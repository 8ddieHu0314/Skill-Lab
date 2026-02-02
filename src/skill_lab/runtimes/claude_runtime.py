"""Claude Code runtime adapter for executing skills."""

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from skill_lab.core.models import TraceEvent
from skill_lab.runtimes.base import RuntimeAdapter


class ClaudeRuntime(RuntimeAdapter):
    """Execute skills via Claude Code CLI and capture traces.

    Claude Code can be run in non-interactive mode with --print and
    --output-format json to capture structured output for analysis.

    Note: Claude Code's trace format differs from Codex. This adapter
    normalizes events to the common TraceEvent format.
    """

    @property
    def name(self) -> str:
        """Return the runtime name."""
        return "claude"

    def execute(
        self,
        prompt: str,
        skill_path: Path,
        trace_path: Path,
        stop_on_skill: str | None = None,
    ) -> int:
        """Run Claude Code with the given prompt.

        Args:
            prompt: The user prompt to send.
            skill_path: Path to the skill directory.
            trace_path: Where to write the trace.
            stop_on_skill: If provided, terminate early when this skill
                is triggered. Optimizes positive trigger tests.

        Returns:
            Exit code from Claude Code.
        """
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        # Get full path to handle Windows .CMD files
        claude_path = shutil.which("claude")
        if claude_path is None:
            trace_path.write_text(
                '{"type": "error", "message": "Claude CLI not found"}\n'
            )
            return 127

        try:
            # Use streaming with Popen for early termination support
            proc = subprocess.Popen(
                [
                    claude_path,
                    "--print",  # Output mode
                    "--verbose",  # Required for stream-json output
                    "--output-format",
                    "stream-json",
                    "-p",
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

        Looks for Skill tool invocations with the specified skill name.

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

        # Skip system init events
        if event.get("type") == "system":
            return False

        # Check for direct Skill tool_use (shouldn't happen at top level, but check)
        if event.get("name") == "Skill":
            tool_input = event.get("input", {})
            if isinstance(tool_input, dict) and tool_input.get("skill") == skill_name:
                return True

        # Check nested in assistant message content
        # Format: {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", ...}]}}
        message = event.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("name") == "Skill":
                        tool_input = item.get("input", {})
                        if isinstance(tool_input, dict) and tool_input.get("skill") == skill_name:
                            return True

        return False

    def _format_trace(self, raw_output: str) -> str:
        """Format raw JSONL output for human readability.

        Converts compact single-line JSON objects to pretty-printed format
        with blank lines between objects.

        Args:
            raw_output: Raw JSONL string from Claude CLI.

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
        """Parse Claude trace into normalized TraceEvent objects.

        Handles both compact JSONL (one object per line) and formatted
        traces (multi-line pretty-printed JSON with blank line separators).

        Filters out stream_event types (text streaming deltas) as they
        are not useful for trace analysis - we only care about tool
        invocations and results.
        """
        if not trace_path.exists():
            return

        content = trace_path.read_text()

        # Split by double newline (formatted) or single newline (compact JSONL)
        # For formatted traces, objects are separated by blank lines
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
                # Skip stream events (text deltas) - not useful for analysis
                if raw.get("type") == "stream_event":
                    continue
                yield self._normalize_event(raw)
            except json.JSONDecodeError:
                continue

    def _normalize_event(self, raw: dict[str, Any]) -> TraceEvent:
        """Convert Claude event to normalized TraceEvent.

        Claude Code stream-json format emits:
        - tool_use: {"type": "tool_use", "id": "...", "name": "Bash", "input": {...}}
        - tool_result: {"type": "tool_result", "tool_use_id": "...", "content": "..."}
        - stream_event: {"type": "stream_event", "event": {...}} (text streaming)
        - result: {"type": "result", ...} (final result)

        Tool names are PascalCase: Bash, Read, Write, Edit, Glob, Grep, etc.
        """
        event_type = raw.get("type", "unknown")

        # Skip stream_event (just text streaming tokens, not actions)
        if event_type == "stream_event":
            return TraceEvent(
                type="stream",
                item_type="text_delta",
                raw=raw,
            )

        # Map Claude event types to our normalized types
        type_mapping = {
            "assistant": "item.completed",
            "tool_use": "item.started",
            "tool_result": "item.completed",
            "message": "turn.completed",
            "result": "turn.completed",
        }

        normalized_type = type_mapping.get(event_type) or event_type

        # Extract command from tool_use events
        command = None
        item_type = None
        if event_type == "tool_use":
            tool_name = raw.get("name", "")
            tool_input = raw.get("input", {})

            # Bash tool - extract command
            if tool_name == "Bash":
                command = tool_input.get("command")
                item_type = "command_execution"
            # File operation tools
            elif tool_name in ("Read", "Write", "Edit"):
                item_type = "file_operation"
                # For Write/Edit, capture the file path as context
                command = tool_input.get("file_path")
            # Other tools (Glob, Grep, WebFetch, etc.)
            else:
                item_type = tool_name.lower()

        # Extract output from tool_result events
        output = None
        if event_type == "tool_result":
            output = raw.get("content")
            # tool_result doesn't carry the tool type, mark as generic
            item_type = "tool_result"

        return TraceEvent(
            type=normalized_type,
            item_type=item_type,
            command=command,
            output=output,
            timestamp=raw.get("timestamp"),
            raw=raw,
        )

    def is_available(self) -> bool:
        """Check if Claude CLI is installed."""
        return shutil.which("claude") is not None
