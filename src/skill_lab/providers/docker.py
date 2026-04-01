"""Docker execution provider — container-based isolation.

Requires: pip install skill-lab[docker]
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tarfile
from pathlib import Path
from typing import Any

from skill_lab.core.exceptions import ProviderError
from skill_lab.providers.base import ExecutionContext, ExecutionProvider
from skill_lab.runtimes.base import RuntimeAdapter

# Container workspace path
_WORKSPACE = "/workspace"
_SKILL_DISCOVERY_PATH = f"{_WORKSPACE}/.claude/skills"

# Skill subdirectories to inject (same as local.py)
_SKILL_SUBDIRS = ("scripts", "assets", "references")

# API key env vars to forward into the container
_API_KEY_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")

# Resource defaults
_DEFAULT_CPU_COUNT = 1
_DEFAULT_MEM_LIMIT = "512m"

# Image tag prefix
_IMAGE_PREFIX = "sklab"


def _build_dockerfile(cli_binary: str) -> str:
    """Build inline Dockerfile content for the given runtime CLI."""
    if cli_binary == "claude":
        npm_package = "@anthropic-ai/claude-code"
    elif cli_binary == "codex":
        npm_package = "@openai/codex"
    else:
        raise ProviderError(
            f"No Docker image recipe for runtime CLI: {cli_binary!r}",
            provider="docker",
            suggestion="Only 'claude' and 'codex' runtimes are supported with Docker",
        )
    return f"FROM node:20-slim\nRUN npm install -g {npm_package}\nWORKDIR {_WORKSPACE}\n"


def _base_image_tag(cli_binary: str) -> str:
    """Deterministic tag for the base image (runtime-specific)."""
    return f"{_IMAGE_PREFIX}-base-{cli_binary}:latest"


def _snapshot_tag(cli_binary: str, skill_name: str) -> str:
    """Tag for the skill-injected snapshot image."""
    return f"{_IMAGE_PREFIX}-snap-{cli_binary}-{skill_name}:latest"


class _ContainerRef:
    """Mutable reference to a running Docker container."""

    __slots__ = ("container_id",)

    def __init__(self, container_id: str) -> None:
        self.container_id = container_id


class DockerProvider(ExecutionProvider):
    """Execution provider that runs agents inside Docker containers.

    Requires: pip install skill-lab[docker]

    Lifecycle:
        setup()         → Build base image, inject skill, commit snapshot
        prepare_test()  → Create container from snapshot
        execute()       → container.exec_run(agent command)
        collect_trace() → Write captured stdout to host trace_path
        cleanup_test()  → Stop + remove container
        teardown()      → Remove snapshot image (keep base for caching)
    """

    def __init__(
        self,
        runtime: RuntimeAdapter,
        *,
        cpu_count: int = _DEFAULT_CPU_COUNT,
        mem_limit: str = _DEFAULT_MEM_LIMIT,
    ) -> None:
        self._runtime = runtime
        self._cpu_count = cpu_count
        self._mem_limit = mem_limit
        self._client: Any = None
        self._snapshot_tag: str | None = None
        self._container_map: dict[Path, _ContainerRef] = {}
        self._captured_output: dict[Path, str] = {}

    @property
    def name(self) -> str:
        return "docker"

    def _get_client(self) -> Any:
        """Lazy-init Docker client with helpful error on failure."""
        if self._client is not None:
            return self._client
        try:
            import docker as docker_lib
        except ImportError:
            raise ProviderError(
                "Docker SDK not installed",
                provider="docker",
                suggestion="Install with: pip install skill-lab[docker]",
            ) from None
        try:
            client = docker_lib.from_env()
            client.ping()
        except Exception as exc:
            raise ProviderError(
                f"Cannot connect to Docker daemon: {exc}",
                provider="docker",
                suggestion="Ensure Docker is running (docker ps) and the current user has access",
            ) from exc
        self._client = client
        return client

    def _image_exists(self, tag: str) -> bool:
        """Check if a Docker image with the given tag exists locally."""
        client = self._get_client()
        try:
            client.images.get(tag)
            return True
        except Exception:
            return False

    def setup(self, skill_path: Path, skill_name: str) -> None:
        """Build base image, inject skill, commit as snapshot."""
        client = self._get_client()
        cli_binary = self._runtime.cli_binary_name

        # Phase 1: Build or reuse base image
        base_tag = _base_image_tag(cli_binary)
        if not self._image_exists(base_tag):
            dockerfile_content = _build_dockerfile(cli_binary)
            fileobj = io.BytesIO(dockerfile_content.encode("utf-8"))
            try:
                client.images.build(fileobj=fileobj, tag=base_tag, rm=True, forcerm=True)
            except Exception as exc:
                raise ProviderError(
                    f"Failed to build Docker base image: {exc}",
                    provider="docker",
                    suggestion="Check Docker build logs and network connectivity",
                ) from exc

        # Phase 2: Create temp container, inject skill via tar
        container = client.containers.create(
            base_tag,
            command="sleep infinity",
            working_dir=_WORKSPACE,
        )
        try:
            container.start()
            self._inject_skill(container, skill_path, skill_name)
            # Phase 3: Commit as snapshot
            snap_tag = _snapshot_tag(cli_binary, skill_name)
            repo, tag = snap_tag.rsplit(":", 1)
            container.commit(repository=repo, tag=tag)
            self._snapshot_tag = snap_tag
        finally:
            container.stop(timeout=5)
            container.remove(force=True)

    def _inject_skill(self, container: Any, skill_path: Path, skill_name: str) -> None:
        """Inject skill files into the container via tar archive."""
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            skill_md = skill_path / "SKILL.md"
            if skill_md.exists():
                tar.add(str(skill_md), arcname=f"{skill_name}/SKILL.md")

            for subdir in _SKILL_SUBDIRS:
                subdir_path = skill_path / subdir
                if subdir_path.is_dir():
                    for file in subdir_path.rglob("*"):
                        if file.is_file():
                            arcname = f"{skill_name}/{subdir}/{file.relative_to(subdir_path)}"
                            tar.add(str(file), arcname=arcname)

        tar_buffer.seek(0)
        container.put_archive(f"{_SKILL_DISCOVERY_PATH}/", tar_buffer.getvalue())

    def prepare_test(
        self,
        skill_path: Path,
        skill_name: str,
        trace_path: Path,
    ) -> ExecutionContext:
        """Create a fresh container from the snapshot image."""
        if self._snapshot_tag is None:
            raise ProviderError(
                "DockerProvider.setup() must be called before prepare_test()",
                provider="docker",
            )
        client = self._get_client()

        env_vars: dict[str, str] = {}
        for var in _API_KEY_VARS:
            value = os.environ.get(var)
            if value:
                env_vars[var] = value

        container = client.containers.create(
            self._snapshot_tag,
            command="sleep infinity",
            working_dir=_WORKSPACE,
            environment=env_vars,
            cpu_count=self._cpu_count,
            mem_limit=self._mem_limit,
        )
        container.start()

        ref = _ContainerRef(container_id=container.id)
        self._container_map[trace_path] = ref

        return ExecutionContext(
            skill_path=skill_path,
            skill_name=skill_name,
            working_dir=Path(_WORKSPACE),
            trace_path=trace_path,
        )

    def execute(
        self,
        context: ExecutionContext,
        runtime: RuntimeAdapter,
        prompt: str,
        stop_on_skill: str | None,
    ) -> int:
        """Run the agent command inside the container."""
        ref = self._container_map.get(context.trace_path)
        if ref is None:
            raise ProviderError(
                "No container found for this test context",
                provider="docker",
            )
        client = self._get_client()
        container = client.containers.get(ref.container_id)

        cli_binary = runtime.cli_binary_name
        command = runtime.build_command(cli_binary, prompt)

        try:
            if stop_on_skill:
                return self._execute_streaming(
                    container, command, runtime, stop_on_skill, context.trace_path
                )
            # Non-streaming: run to completion
            exit_code_raw, output = container.exec_run(command, workdir=_WORKSPACE, demux=False)
            raw_output = output.decode("utf-8", errors="replace") if output else ""
            self._captured_output[context.trace_path] = raw_output
            return int(exit_code_raw)
        except ProviderError:
            raise
        except Exception as exc:
            error_trace = (
                json.dumps({"type": "error", "message": f"Container execution failed: {exc}"})
                + "\n"
            )
            self._captured_output[context.trace_path] = error_trace
            return 1

    def _execute_streaming(
        self,
        container: Any,
        command: list[str],
        runtime: RuntimeAdapter,
        stop_on_skill: str,
        trace_path: Path,
    ) -> int:
        """Execute with streaming to support early termination on skill trigger."""
        exec_result = container.client.api.exec_create(
            container.id,
            command,
            workdir=_WORKSPACE,
            stdout=True,
            stderr=True,
        )
        exec_id = exec_result["Id"]
        output_gen = container.client.api.exec_start(exec_id, stream=True)

        captured_lines: list[str] = []
        buffer = ""
        skill_triggered = False

        for chunk in output_gen:
            text = chunk.decode("utf-8", errors="replace")
            buffer += text
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                captured_lines.append(line)

                if not skill_triggered and runtime.check_skill_trigger(line, stop_on_skill):
                    skill_triggered = True
                    break
            if skill_triggered:
                break

        if buffer.strip():
            captured_lines.append(buffer.strip())

        self._captured_output[trace_path] = "\n".join(captured_lines)

        if skill_triggered:
            # Stop the container to kill the exec process and prevent
            # further API calls from burning tokens between detection
            # and cleanup_test().
            with contextlib.suppress(Exception):
                container.stop(timeout=2)
            return 0

        inspect = container.client.api.exec_inspect(exec_id)
        return int(inspect.get("ExitCode", 0))

    def collect_trace(self, context: ExecutionContext) -> Path:
        """Write captured container output to the host trace path."""
        raw_output = self._captured_output.pop(context.trace_path, "")
        formatted = self._runtime.format_trace(raw_output)
        context.trace_path.parent.mkdir(parents=True, exist_ok=True)
        context.trace_path.write_text(formatted)
        return context.trace_path

    def cleanup_test(self, context: ExecutionContext) -> None:
        """Stop and remove the container."""
        ref = self._container_map.pop(context.trace_path, None)
        if ref is None:
            return
        try:
            client = self._get_client()
            container = client.containers.get(ref.container_id)
            container.stop(timeout=5)
            container.remove(force=True)
        except Exception:
            pass

    def teardown(self) -> None:
        """Remove snapshot image, clean up leftover containers."""
        if self._client is None:
            return

        client = self._client

        # Clean up leftover containers
        for ref in self._container_map.values():
            try:
                container = client.containers.get(ref.container_id)
                container.stop(timeout=2)
                container.remove(force=True)
            except Exception:
                pass
        self._container_map.clear()
        self._captured_output.clear()

        # Remove snapshot image (keep base for caching)
        if self._snapshot_tag:
            with contextlib.suppress(Exception):
                client.images.remove(self._snapshot_tag, force=True)
            self._snapshot_tag = None
