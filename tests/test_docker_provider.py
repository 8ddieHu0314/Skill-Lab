"""Unit tests for skill_lab.providers.docker — DockerProvider.

All tests mock the Docker SDK so they run without Docker installed.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skill_lab.core.exceptions import ProviderError
from skill_lab.core.models import TraceEvent
from skill_lab.providers.docker import (
    DockerProvider,
    _SKILL_DISCOVERY_PATH,
    _WORKSPACE,
    _base_image_tag,
    _build_dockerfile,
    _snapshot_tag,
)
from skill_lab.runtimes.base import RuntimeAdapter


# ─── Test doubles ─────────────────────────────────────────────────────────────


class FakeRuntime(RuntimeAdapter):
    """Minimal runtime for testing DockerProvider."""

    def __init__(self, binary: str = "claude") -> None:
        self._binary = binary

    @property
    def name(self) -> str:
        return self._binary

    def _cli_binary_name(self) -> str:
        return self._binary

    def _build_command(self, cli_path: str, prompt: str) -> list[str]:
        return [cli_path, "--print", "-p", prompt]

    def _check_skill_trigger(self, line: str, skill_name: str) -> bool:
        return f'"skill": "{skill_name}"' in line

    def execute(
        self,
        prompt: str,
        skill_path: Path,
        trace_path: Path,
        stop_on_skill: str | None = None,
        working_dir: Path | None = None,
    ) -> int:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text("")
        return 0

    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]:
        return iter([])


def _mock_docker_client() -> MagicMock:
    """Create a mock Docker client with realistic API surface."""
    client = MagicMock()
    client.ping.return_value = True

    # Mock image operations
    mock_image = MagicMock()
    client.images.build.return_value = (mock_image, [])
    client.images.get.return_value = mock_image

    # Mock container operations
    mock_container = MagicMock()
    mock_container.id = "abc123"
    mock_container.start.return_value = None
    mock_container.stop.return_value = None
    mock_container.remove.return_value = None
    mock_container.put_archive.return_value = True
    mock_container.commit.return_value = mock_image
    mock_container.exec_run.return_value = (0, b'{"type": "result"}\n')
    client.containers.create.return_value = mock_container
    client.containers.get.return_value = mock_container

    return client


# ─── Helper functions ─────────────────────────────────────────────────────────


class TestBuildDockerfile:
    def test_claude(self) -> None:
        df = _build_dockerfile("claude")
        assert "node:20-slim" in df
        assert "@anthropic-ai/claude-code" in df
        assert _WORKSPACE in df

    def test_codex(self) -> None:
        df = _build_dockerfile("codex")
        assert "node:20-slim" in df
        assert "@openai/codex" in df

    def test_unknown_raises(self) -> None:
        with pytest.raises(ProviderError, match="No Docker image recipe"):
            _build_dockerfile("unknown-cli")


class TestImageTags:
    def test_base_tag_format(self) -> None:
        assert _base_image_tag("claude") == "sklab-base-claude:latest"
        assert _base_image_tag("codex") == "sklab-base-codex:latest"

    def test_snapshot_tag_includes_skill_name(self) -> None:
        tag = _snapshot_tag("claude", "my-skill")
        assert tag == "sklab-snap-claude-my-skill:latest"


# ─── DockerProvider ───────────────────────────────────────────────────────────


class TestDockerProviderInit:
    def test_name_returns_docker(self) -> None:
        provider = DockerProvider(FakeRuntime())
        assert provider.name == "docker"

    def test_get_client_import_error(self) -> None:
        provider = DockerProvider(FakeRuntime())
        with patch.dict("sys.modules", {"docker": None}):
            with pytest.raises(ProviderError, match="Docker SDK not installed"):
                provider._get_client()

    def test_get_client_connection_error(self) -> None:
        provider = DockerProvider(FakeRuntime())
        mock_docker = MagicMock()
        mock_docker.from_env.side_effect = Exception("Cannot connect")
        with patch.dict("sys.modules", {"docker": mock_docker}):
            with pytest.raises(ProviderError, match="Cannot connect to Docker daemon"):
                provider._get_client()


class TestDockerProviderSetup:
    def test_builds_image_and_injects_skill(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "my-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("---\nname: my-skill\n---\nBody")

        client = _mock_docker_client()
        # Image does NOT exist yet → build it
        client.images.get.side_effect = Exception("not found")

        provider = DockerProvider(FakeRuntime())
        provider._client = client

        provider.setup(skill_path, "my-skill")

        # Verify image was built
        client.images.build.assert_called_once()
        # Verify container was created, started, committed, and cleaned up
        client.containers.create.assert_called()
        container = client.containers.create.return_value
        container.start.assert_called_once()
        container.put_archive.assert_called_once()
        container.commit.assert_called_once()
        container.stop.assert_called_once()
        container.remove.assert_called_once()

        assert provider._snapshot_tag is not None

    def test_reuses_existing_base_image(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "my-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("content")

        client = _mock_docker_client()
        # Image already exists → skip build
        client.images.get.return_value = MagicMock()

        provider = DockerProvider(FakeRuntime())
        provider._client = client

        provider.setup(skill_path, "my-skill")

        # build should NOT be called since base image exists
        client.images.build.assert_not_called()

    def test_build_failure_raises(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("x")

        client = _mock_docker_client()
        client.images.get.side_effect = Exception("not found")
        client.images.build.side_effect = Exception("Build failed: network error")

        provider = DockerProvider(FakeRuntime())
        provider._client = client

        with pytest.raises(ProviderError, match="Failed to build"):
            provider.setup(skill_path, "skill")


class TestDockerProviderPrepareTest:
    def test_creates_container_from_snapshot(self, tmp_path: Path) -> None:
        client = _mock_docker_client()
        provider = DockerProvider(FakeRuntime())
        provider._client = client
        provider._snapshot_tag = "sklab-snap-claude-my-skill:latest"

        trace_path = tmp_path / "traces" / "test.jsonl"
        ctx = provider.prepare_test(tmp_path / "skill", "my-skill", trace_path)

        assert ctx.working_dir == Path(_WORKSPACE)
        assert ctx.trace_path == trace_path
        client.containers.create.assert_called_once()
        # Verify snapshot tag used
        call_args = client.containers.create.call_args
        assert call_args[0][0] == "sklab-snap-claude-my-skill:latest"

    def test_without_setup_raises(self, tmp_path: Path) -> None:
        provider = DockerProvider(FakeRuntime())
        provider._client = _mock_docker_client()

        with pytest.raises(ProviderError, match="setup\\(\\) must be called"):
            provider.prepare_test(tmp_path, "skill", tmp_path / "t.jsonl")

    def test_forwards_api_keys(self, tmp_path: Path) -> None:
        client = _mock_docker_client()
        provider = DockerProvider(FakeRuntime())
        provider._client = client
        provider._snapshot_tag = "snap:latest"

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test", "OPENAI_API_KEY": "sk-oai"}):
            provider.prepare_test(tmp_path, "skill", tmp_path / "t.jsonl")

        call_kwargs = client.containers.create.call_args[1]
        env = call_kwargs["environment"]
        assert env["ANTHROPIC_API_KEY"] == "sk-test"
        assert env["OPENAI_API_KEY"] == "sk-oai"

    def test_resource_limits_passed(self, tmp_path: Path) -> None:
        client = _mock_docker_client()
        provider = DockerProvider(FakeRuntime(), cpu_count=2, mem_limit="1g")
        provider._client = client
        provider._snapshot_tag = "snap:latest"

        provider.prepare_test(tmp_path, "skill", tmp_path / "t.jsonl")

        call_kwargs = client.containers.create.call_args[1]
        assert call_kwargs["cpu_count"] == 2
        assert call_kwargs["mem_limit"] == "1g"


class TestDockerProviderExecute:
    def _setup_provider(self, tmp_path: Path) -> tuple[DockerProvider, MagicMock, Path]:
        client = _mock_docker_client()
        provider = DockerProvider(FakeRuntime())
        provider._client = client
        provider._snapshot_tag = "snap:latest"

        trace_path = tmp_path / "t.jsonl"
        provider.prepare_test(tmp_path / "skill", "my-skill", trace_path)
        return provider, client, trace_path

    def test_non_streaming_execution(self, tmp_path: Path) -> None:
        provider, client, trace_path = self._setup_provider(tmp_path)
        container = client.containers.get.return_value
        container.exec_run.return_value = (0, b'{"type": "result"}\n')

        runtime = FakeRuntime()
        ctx = provider.prepare_test(tmp_path / "skill", "s", trace_path)
        # Need to set up the container ref for the new trace_path
        exit_code = provider.execute(ctx, runtime, "do something", stop_on_skill=None)

        assert exit_code == 0
        assert trace_path in provider._captured_output

    def test_execution_failure_returns_error(self, tmp_path: Path) -> None:
        provider, client, trace_path = self._setup_provider(tmp_path)
        container = client.containers.get.return_value
        container.exec_run.side_effect = RuntimeError("container crashed")

        runtime = FakeRuntime()
        ctx = provider.prepare_test(tmp_path / "skill", "s", trace_path)
        exit_code = provider.execute(ctx, runtime, "prompt", stop_on_skill=None)

        assert exit_code == 1
        assert "container crashed" in provider._captured_output.get(trace_path, "")

    def test_streaming_early_termination(self, tmp_path: Path) -> None:
        client = _mock_docker_client()
        provider = DockerProvider(FakeRuntime())
        provider._client = client
        provider._snapshot_tag = "snap:latest"

        trace_path = tmp_path / "t.jsonl"
        ctx = provider.prepare_test(tmp_path / "skill", "my-skill", trace_path)

        container = client.containers.get.return_value
        # Mock the low-level exec API for streaming
        container.client.api.exec_create.return_value = {"Id": "exec123"}
        container.client.api.exec_start.return_value = iter(
            [
                b'{"type": "thinking"}\n',
                b'{"type": "tool_use", "skill": "my-skill"}\n',
                b'{"type": "more_output"}\n',  # Should not be reached
            ]
        )

        runtime = FakeRuntime()
        exit_code = provider.execute(ctx, runtime, "prompt", stop_on_skill="my-skill")

        assert exit_code == 0
        output = provider._captured_output[trace_path]
        assert '"thinking"' in output
        assert '"skill": "my-skill"' in output


class TestDockerProviderCollectTrace:
    def test_writes_formatted_trace_to_host(self, tmp_path: Path) -> None:
        provider = DockerProvider(FakeRuntime())
        trace_path = tmp_path / "traces" / "test.jsonl"
        provider._captured_output[trace_path] = '{"type": "result"}\n{"type": "done"}'

        ctx = MagicMock()
        ctx.trace_path = trace_path

        result = provider.collect_trace(ctx)

        assert result == trace_path
        assert trace_path.exists()
        content = trace_path.read_text()
        assert "result" in content


class TestDockerProviderCleanup:
    def test_stops_and_removes_container(self, tmp_path: Path) -> None:
        client = _mock_docker_client()
        provider = DockerProvider(FakeRuntime())
        provider._client = client
        provider._snapshot_tag = "snap:latest"

        trace_path = tmp_path / "t.jsonl"
        ctx = provider.prepare_test(tmp_path / "skill", "s", trace_path)
        provider.cleanup_test(ctx)

        container = client.containers.get.return_value
        container.stop.assert_called()
        container.remove.assert_called()
        assert trace_path not in provider._container_map

    def test_handles_missing_container(self, tmp_path: Path) -> None:
        provider = DockerProvider(FakeRuntime())
        ctx = MagicMock()
        ctx.trace_path = tmp_path / "nonexistent.jsonl"
        provider.cleanup_test(ctx)  # Must not raise


class TestDockerProviderTeardown:
    def test_removes_snapshot_image(self) -> None:
        client = _mock_docker_client()
        provider = DockerProvider(FakeRuntime())
        provider._client = client
        provider._snapshot_tag = "sklab-snap-claude-skill:latest"

        provider.teardown()

        client.images.remove.assert_called_once_with(
            "sklab-snap-claude-skill:latest", force=True
        )
        assert provider._snapshot_tag is None

    def test_teardown_without_client_is_noop(self) -> None:
        provider = DockerProvider(FakeRuntime())
        provider.teardown()  # Must not raise

    def test_cleans_leftover_containers(self, tmp_path: Path) -> None:
        client = _mock_docker_client()
        provider = DockerProvider(FakeRuntime())
        provider._client = client
        provider._snapshot_tag = "snap:latest"

        # Simulate leftover container
        from skill_lab.providers.docker import _ContainerRef

        provider._container_map[tmp_path / "t.jsonl"] = _ContainerRef("leftover123")

        provider.teardown()

        # Should have tried to clean up the leftover
        client.containers.get.assert_called()
        assert len(provider._container_map) == 0
