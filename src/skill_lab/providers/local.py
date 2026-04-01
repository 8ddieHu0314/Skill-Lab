"""Local execution provider — temp directory isolation."""

import contextlib
import shutil
import tempfile
from pathlib import Path

from skill_lab.providers.base import ExecutionContext, ExecutionProvider
from skill_lab.runtimes.base import RuntimeAdapter

# Skill subdirectories to copy into the isolated environment.
_SKILL_SUBDIRS = ("scripts", "assets", "references")


class LocalProvider(ExecutionProvider):
    """Execution provider that runs agents in isolated temp directories.

    For each test, creates a fresh temp directory with the skill copied
    into .claude/skills/<skill_name>/. The agent runs from this directory,
    preventing file system side effects from leaking between tests or
    modifying the real project.

    This is the default provider — zero external dependencies required.
    """

    @property
    def name(self) -> str:
        return "local"

    def prepare_test(
        self,
        skill_path: Path,
        skill_name: str,
        trace_path: Path,
    ) -> ExecutionContext:
        """Create a temp directory with the skill copied into the discovery path."""
        temp_dir = Path(tempfile.mkdtemp(prefix="sklab-"))

        # Create the skill discovery path: .claude/skills/<skill_name>/
        discovery_dir = temp_dir / ".claude" / "skills" / skill_name
        discovery_dir.mkdir(parents=True)

        with contextlib.suppress(FileNotFoundError):
            shutil.copy2(skill_path / "SKILL.md", discovery_dir / "SKILL.md")

        for subdir in _SKILL_SUBDIRS:
            with contextlib.suppress(FileNotFoundError):
                shutil.copytree(skill_path / subdir, discovery_dir / subdir)

        return ExecutionContext(
            skill_path=skill_path,
            skill_name=skill_name,
            working_dir=temp_dir,
            trace_path=trace_path,
        )

    def execute(
        self,
        context: ExecutionContext,
        runtime: RuntimeAdapter,
        prompt: str,
        stop_on_skill: str | None,
    ) -> int:
        """Delegate to the runtime adapter with working_dir set to the temp directory."""
        return runtime.execute(
            prompt=prompt,
            skill_path=context.skill_path,
            trace_path=context.trace_path,
            stop_on_skill=stop_on_skill,
            working_dir=context.working_dir,
        )

    def cleanup_test(self, context: ExecutionContext) -> None:
        """Remove the temp directory."""
        shutil.rmtree(context.working_dir, ignore_errors=True)
