"""Abstract base class for runtime adapters."""

import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from skill_lab.core.models import TraceEvent


class RuntimeAdapter(ABC):
    """Abstract base class for agent runtime adapters.

    Runtime adapters execute skills with given prompts and capture execution
    traces for analysis. Each runtime (Codex, Claude, etc.) has its own
    native trace format which gets normalized to TraceEvent objects.

    Implementations must provide:
    - name: Runtime adapter name
    - _cli_binary_name(): CLI binary to locate via shutil.which
    - _build_command(): Runtime-specific command args
    - _check_skill_trigger(): Runtime-specific skill detection logic
    - parse_trace(): Trace parsing and normalization
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the runtime adapter name (e.g., 'codex', 'claude')."""
        ...

    @abstractmethod
    def _cli_binary_name(self) -> str:
        """Return the CLI binary name (e.g., 'claude', 'codex')."""
        ...

    @abstractmethod
    def _build_command(self, cli_path: str, prompt: str) -> list[str]:
        """Build the command list for subprocess.Popen.

        Args:
            cli_path: Full path to the CLI binary.
            prompt: The user prompt to send.

        Returns:
            Command list for Popen.
        """
        ...

    @abstractmethod
    def _check_skill_trigger(self, line: str, skill_name: str) -> bool:
        """Check if a JSONL line indicates the skill was triggered.

        Args:
            line: A single line of JSONL output.
            skill_name: The skill name to look for.

        Returns:
            True if the skill was triggered in this event.
        """
        ...

    def execute(
        self,
        prompt: str,
        skill_path: Path,
        trace_path: Path,
        stop_on_skill: str | None = None,
        working_dir: Path | None = None,
    ) -> int:
        """Execute a skill with the given prompt and capture the trace.

        Template method: uses _cli_binary_name(), _build_command(), and
        _check_skill_trigger() from subclasses.

        Args:
            prompt: The user prompt to send to the LLM.
            skill_path: Path to the skill directory (for metadata).
            trace_path: Where to write the execution trace.
            stop_on_skill: If provided, terminate execution early when
                this skill is triggered. Used to optimize positive trigger
                tests by avoiding unnecessary API calls after detection.
            working_dir: Directory to run from. If None, defaults to skill_path.
                For implicit tests, this should be the project root so Claude
                must discover the skill via the Skill tool.

        Returns:
            Exit code from the runtime (0 for success).
        """
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        cwd = working_dir if working_dir is not None else skill_path

        binary = self._cli_binary_name()
        cli_path = shutil.which(binary)
        if cli_path is None:
            trace_path.write_text(
                f'{{"type": "error", "message": "{binary.capitalize()} CLI not found"}}\n'
            )
            return 127

        try:
            proc = subprocess.Popen(
                self._build_command(cli_path, prompt),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
            )

            captured_lines: list[str] = []
            skill_triggered = False

            for line in proc.stdout or []:
                line = line.rstrip("\n")
                if not line:
                    continue
                captured_lines.append(line)

                if (
                    stop_on_skill
                    and not skill_triggered
                    and self._check_skill_trigger(line, stop_on_skill)
                ):
                    skill_triggered = True
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    break

            if proc.poll() is None:
                try:
                    proc.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    captured_lines.append('{"type": "error", "message": "Execution timed out"}')

            formatted_trace = self._format_trace("\n".join(captured_lines))
            trace_path.write_text(formatted_trace)

            if skill_triggered:
                return 0
            return proc.returncode or 0

        except Exception as e:
            trace_path.write_text(
                f'{{\n  "type": "error",\n  "message": "Execution failed: {e}"\n}}\n'
            )
            return 1

    @abstractmethod
    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]:
        """Parse a trace file into normalized TraceEvent objects.

        Args:
            trace_path: Path to the trace file to parse.

        Yields:
            TraceEvent objects representing each event in the trace.
        """
        ...

    def is_available(self) -> bool:
        """Check if this runtime is available on the system.

        Override this method to check for CLI tools, API keys, etc.
        Default implementation returns True.
        """
        return True

    def _format_trace(self, raw_output: str) -> str:
        """Format raw JSONL output for human readability.

        Converts compact single-line JSON objects to pretty-printed format
        with blank lines between objects.

        Args:
            raw_output: Raw JSONL string from CLI.

        Returns:
            Formatted trace string with pretty-printed JSON objects.
        """
        formatted_objects: list[str] = []
        for line in raw_output.strip().split("\n"):
            if not line:
                continue
            try:
                obj = json.loads(line)
                formatted_objects.append(json.dumps(obj, indent=2))
            except json.JSONDecodeError:
                # Keep malformed lines as-is
                formatted_objects.append(line)

        return "\n\n".join(formatted_objects) + "\n" if formatted_objects else ""

    def _parse_trace_chunks(self, trace_path: Path) -> Iterator[dict[str, Any]]:
        """Parse trace file into raw JSON objects.

        Handles both compact JSONL (one object per line) and formatted
        traces (multi-line pretty-printed JSON with blank line separators).

        Args:
            trace_path: Path to the trace file.

        Yields:
            Parsed JSON objects from the trace.
        """
        if not trace_path.exists():
            return

        content = trace_path.read_text()

        # Split by double newline (formatted) or single newline (compact JSONL)
        chunks = content.split("\n\n") if "\n\n" in content else content.strip().split("\n")

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                yield json.loads(chunk)
            except json.JSONDecodeError:
                continue
