"""Codex CLI runtime adapter for executing skills."""

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from skill_lab.core.models import TraceEvent
from skill_lab.runtimes.base import RuntimeAdapter


class CodexRuntime(RuntimeAdapter):
    """Execute skills via OpenAI Codex CLI and capture JSONL traces.

    The Codex CLI emits structured JSONL events when run with --json flag.
    This adapter captures those events and normalizes them to TraceEvent
    objects for analysis.

    Event types from Codex:
    - item.started: Command/action began
    - item.completed: Command/action finished
    - turn.started: Agent turn began
    - turn.completed: Agent turn finished
    """

    @property
    def name(self) -> str:
        """Return the runtime name."""
        return "codex"

    def execute(
        self,
        prompt: str,
        skill_path: Path,
        trace_path: Path,
        stop_on_skill: str | None = None,
    ) -> int:
        """Run Codex with the given prompt, capturing structured events.

        Args:
            prompt: The user prompt to send.
            skill_path: Path to the skill directory.
            trace_path: Where to write the JSONL trace.
            stop_on_skill: If provided, terminate early when this skill
                is triggered. Optimizes positive trigger tests.

        Returns:
            Exit code from Codex.
        """
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        # Get full path to handle Windows .CMD files
        codex_path = shutil.which("codex")
        if codex_path is None:
            trace_path.write_text(
                '{"type": "error", "message": "Codex CLI not found"}\n'
            )
            return 127

        try:
            # Use streaming with Popen for early termination support
            proc = subprocess.Popen(
                [
                    codex_path,
                    "exec",
                    "--json",  # REQUIRED: emit structured events
                    "--full-auto",  # Allow file system changes
                    prompt,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=skill_path,
            )

            captured_lines: list[str] = []
            skill_triggered = False

            # Stream stdout and check for skill trigger
            for line in proc.stdout or []:
                line = line.rstrip("\n")
                if not line:
                    continue
                captured_lines.append(line)

                # Check if we should stop early
                if stop_on_skill and not skill_triggered:
                    if self._check_skill_trigger(line, stop_on_skill):
                        skill_triggered = True
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        break

            # Wait for process to complete if not terminated
            if proc.poll() is None:
                try:
                    proc.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    captured_lines.append('{"type": "error", "message": "Execution timed out"}')

            # Format trace for readability
            formatted_trace = self._format_trace("\n".join(captured_lines))
            trace_path.write_text(formatted_trace)

            # Return 0 if we terminated early due to skill trigger (success)
            if skill_triggered:
                return 0
            return proc.returncode or 0

        except Exception as e:
            trace_path.write_text(
                f'{{\n  "type": "error",\n  "message": "Execution failed: {e}"\n}}\n'
            )
            return 1

    def _check_skill_trigger(self, line: str, skill_name: str) -> bool:
        """Check if a JSONL line indicates the skill was triggered.

        Looks for skill invocation events with the specified skill name.
        Codex may use different event formats than Claude.

        Args:
            line: A single line of JSONL output.
            skill_name: The skill name to look for.

        Returns:
            True if the skill was triggered in this event.
        """
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return False

        # Check for skill_invocation item type (Codex format)
        item = event.get("item", {})
        if item.get("type") == "skill_invocation":
            if skill_name in (item.get("command") or ""):
                return True

        # Check for explicit $skill-name or skill:skill-name patterns
        raw_str = str(event)
        if f"${skill_name}" in raw_str or f"skill:{skill_name}" in raw_str:
            return True

        return False

    def _format_trace(self, raw_output: str) -> str:
        """Format raw JSONL output for human readability.

        Converts compact single-line JSON objects to pretty-printed format
        with blank lines between objects.

        Args:
            raw_output: Raw JSONL string from Codex CLI.

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

    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]:
        """Parse trace into normalized TraceEvent objects.

        Handles both compact JSONL (one object per line) and formatted
        traces (multi-line pretty-printed JSON with blank line separators).
        """
        if not trace_path.exists():
            return

        content = trace_path.read_text()

        # Split by double newline (formatted) or single newline (compact JSONL)
        if "\n\n" in content:
            # Formatted trace: split by blank lines
            chunks = content.split("\n\n")
        else:
            # Compact JSONL: split by single newlines
            chunks = content.strip().split("\n")

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                raw = json.loads(chunk)
                yield self._normalize_event(raw)
            except json.JSONDecodeError:
                # Skip malformed lines
                continue

    def _normalize_event(self, raw: dict[str, Any]) -> TraceEvent:
        """Convert Codex event to normalized TraceEvent."""
        item = raw.get("item", {})

        return TraceEvent(
            type=raw.get("type", "unknown"),
            item_type=item.get("type"),
            command=item.get("command"),
            output=item.get("output"),
            timestamp=raw.get("timestamp"),
            raw=raw,
        )

    def is_available(self) -> bool:
        """Check if Codex CLI is installed."""
        return shutil.which("codex") is not None
