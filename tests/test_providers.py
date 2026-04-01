"""Unit tests for skill_lab.providers — ExecutionContext and LocalProvider."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from skill_lab.core.models import TraceEvent
from skill_lab.providers.base import ExecutionContext, ExecutionProvider
from skill_lab.providers.local import LocalProvider
from skill_lab.runtimes.base import RuntimeAdapter


# ─── Test doubles ─────────────────────────────────────────────────────────────


class FakeRuntime(RuntimeAdapter):
    """Minimal runtime for testing provider delegation."""

    def __init__(self, exit_code: int = 0) -> None:
        self._exit_code = exit_code
        self.last_working_dir: Path | None = None

    @property
    def name(self) -> str:
        return "fake"

    def _cli_binary_name(self) -> str:
        return "fake"

    def _build_command(self, cli_path: str, prompt: str) -> list[str]:
        return [cli_path, prompt]

    def _check_skill_trigger(self, line: str, skill_name: str) -> bool:
        return False

    def execute(
        self,
        prompt: str,
        skill_path: Path,
        trace_path: Path,
        stop_on_skill: str | None = None,
        working_dir: Path | None = None,
    ) -> int:
        self.last_working_dir = working_dir
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text("")
        return self._exit_code

    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]:
        return iter([])


# ─── ExecutionContext ─────────────────────────────────────────────────────────


class TestExecutionContext:
    def test_fields(self, tmp_path: Path) -> None:
        ctx = ExecutionContext(
            skill_path=tmp_path / "skill",
            skill_name="my-skill",
            working_dir=tmp_path / "work",
            trace_path=tmp_path / "trace.jsonl",
        )
        assert ctx.skill_name == "my-skill"
        assert ctx.working_dir == tmp_path / "work"
        assert ctx.trace_path == tmp_path / "trace.jsonl"

    def test_frozen(self, tmp_path: Path) -> None:
        ctx = ExecutionContext(
            skill_path=tmp_path,
            skill_name="s",
            working_dir=tmp_path,
            trace_path=tmp_path / "t",
        )
        with pytest.raises(AttributeError):
            ctx.skill_name = "other"  # type: ignore[misc]


# ─── LocalProvider ────────────────────────────────────────────────────────────


class TestLocalProvider:
    def test_name(self) -> None:
        assert LocalProvider().name == "local"

    def test_prepare_creates_temp_dir_with_skill(self, tmp_path: Path) -> None:
        # Create a skill directory with SKILL.md
        skill_path = tmp_path / "my-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("---\nname: my-skill\n---\nBody")

        provider = LocalProvider()
        trace_path = tmp_path / "traces" / "test.jsonl"
        ctx = provider.prepare_test(skill_path, "my-skill", trace_path)

        # Verify temp dir was created
        assert ctx.working_dir.exists()
        assert ctx.working_dir != skill_path

        # Verify skill is in the discovery path
        discovered = ctx.working_dir / ".claude" / "skills" / "my-skill" / "SKILL.md"
        assert discovered.exists()
        assert "Body" in discovered.read_text()

        # Cleanup
        provider.cleanup_test(ctx)

    def test_prepare_copies_scripts_and_assets(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "my-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("content")

        # Create scripts/ and assets/ subdirs
        scripts_dir = skill_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.sh").write_text("#!/bin/bash\necho hi")

        assets_dir = skill_path / "assets"
        assets_dir.mkdir()
        (assets_dir / "data.json").write_text("{}")

        provider = LocalProvider()
        ctx = provider.prepare_test(skill_path, "my-skill", tmp_path / "t.jsonl")

        discovery = ctx.working_dir / ".claude" / "skills" / "my-skill"
        assert (discovery / "scripts" / "run.sh").exists()
        assert (discovery / "assets" / "data.json").exists()

        provider.cleanup_test(ctx)

    def test_prepare_copies_references(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "my-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("content")
        refs_dir = skill_path / "references"
        refs_dir.mkdir()
        (refs_dir / "spec.md").write_text("spec content")

        provider = LocalProvider()
        ctx = provider.prepare_test(skill_path, "my-skill", tmp_path / "t.jsonl")

        discovery = ctx.working_dir / ".claude" / "skills" / "my-skill"
        assert (discovery / "references" / "spec.md").exists()

        provider.cleanup_test(ctx)

    def test_prepare_skips_missing_subdirs(self, tmp_path: Path) -> None:
        """No error if scripts/assets/references don't exist."""
        skill_path = tmp_path / "my-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("content")

        provider = LocalProvider()
        ctx = provider.prepare_test(skill_path, "my-skill", tmp_path / "t.jsonl")

        discovery = ctx.working_dir / ".claude" / "skills" / "my-skill"
        assert (discovery / "SKILL.md").exists()
        assert not (discovery / "scripts").exists()
        assert not (discovery / "assets").exists()

        provider.cleanup_test(ctx)

    def test_execute_delegates_to_runtime(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("x")

        provider = LocalProvider()
        trace_path = tmp_path / "traces" / "test.jsonl"
        ctx = provider.prepare_test(skill_path, "my-skill", trace_path)

        runtime = FakeRuntime(exit_code=42)
        exit_code = provider.execute(ctx, runtime, "do something", stop_on_skill=None)

        assert exit_code == 42
        assert runtime.last_working_dir == ctx.working_dir

        provider.cleanup_test(ctx)

    def test_execute_passes_stop_on_skill(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("x")

        provider = LocalProvider()
        ctx = provider.prepare_test(skill_path, "my-skill", tmp_path / "t.jsonl")

        mock_runtime = MagicMock(spec=RuntimeAdapter)
        mock_runtime.execute.return_value = 0

        provider.execute(ctx, mock_runtime, "prompt", stop_on_skill="my-skill")

        mock_runtime.execute.assert_called_once_with(
            prompt="prompt",
            skill_path=skill_path,
            trace_path=ctx.trace_path,
            stop_on_skill="my-skill",
            working_dir=ctx.working_dir,
        )

        provider.cleanup_test(ctx)

    def test_cleanup_removes_temp_dir(self, tmp_path: Path) -> None:
        skill_path = tmp_path / "skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("x")

        provider = LocalProvider()
        ctx = provider.prepare_test(skill_path, "my-skill", tmp_path / "t.jsonl")

        work_dir = ctx.working_dir
        assert work_dir.exists()

        provider.cleanup_test(ctx)
        assert not work_dir.exists()

    def test_cleanup_handles_missing_dir(self, tmp_path: Path) -> None:
        """No error if the temp dir was already removed."""
        ctx = ExecutionContext(
            skill_path=tmp_path,
            skill_name="x",
            working_dir=tmp_path / "nonexistent",
            trace_path=tmp_path / "t.jsonl",
        )
        provider = LocalProvider()
        provider.cleanup_test(ctx)  # Must not raise

    def test_setup_and_teardown_are_noop(self, tmp_path: Path) -> None:
        provider = LocalProvider()
        provider.setup(tmp_path, "skill")  # Must not raise
        provider.teardown()  # Must not raise

    def test_collect_trace_returns_trace_path(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "trace.jsonl"
        ctx = ExecutionContext(
            skill_path=tmp_path,
            skill_name="s",
            working_dir=tmp_path,
            trace_path=trace_path,
        )
        provider = LocalProvider()
        assert provider.collect_trace(ctx) == trace_path


# ─── ExecutionProvider ABC ────────────────────────────────────────────────────


class TestExecutionProviderABC:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            ExecutionProvider()  # type: ignore[abstract]

    def test_default_setup_is_noop(self, tmp_path: Path) -> None:
        """Concrete subclass inherits no-op setup()."""

        class MinimalProvider(ExecutionProvider):
            @property
            def name(self) -> str:
                return "minimal"

            def prepare_test(self, skill_path: Path, skill_name: str, trace_path: Path):  # type: ignore[override]
                return ExecutionContext(
                    skill_path=skill_path,
                    skill_name=skill_name,
                    working_dir=tmp_path,
                    trace_path=trace_path,
                )

            def execute(self, context, runtime, prompt, stop_on_skill):  # type: ignore[override]
                return 0

            def cleanup_test(self, context):  # type: ignore[override]
                pass

        p = MinimalProvider()
        p.setup(tmp_path, "s")  # Should not raise
        p.teardown()  # Should not raise
