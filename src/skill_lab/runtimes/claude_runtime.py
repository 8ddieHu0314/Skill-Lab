"""Claude Code runtime adapter for executing skills."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterator

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
    ) -> int:
        """Run Claude Code with the given prompt.

        Args:
            prompt: The user prompt to send.
            skill_path: Path to the skill directory.
            trace_path: Where to write the trace.

        Returns:
            Exit code from Claude Code.
        """
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                [
                    "claude",
                    "--print",  # Output mode
                    "--output-format",
                    "stream-json",
                    "-p",
                    prompt,
                ],
                capture_output=True,
                text=True,
                cwd=skill_path,
                timeout=300,  # 5 minute timeout
            )

            trace_path.write_text(result.stdout)
            return result.returncode

        except subprocess.TimeoutExpired:
            trace_path.write_text('{"type": "error", "message": "Execution timed out"}\n')
            return 124

        except FileNotFoundError:
            trace_path.write_text(
                '{"type": "error", "message": "Claude CLI not found"}\n'
            )
            return 127

    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]:
        """Parse Claude trace into normalized TraceEvent objects."""
        if not trace_path.exists():
            return

        content = trace_path.read_text()
        for line in content.strip().split("\n"):
            if not line:
                continue
            try:
                raw = json.loads(line)
                yield self._normalize_event(raw)
            except json.JSONDecodeError:
                continue

    def _normalize_event(self, raw: dict[str, Any]) -> TraceEvent:
        """Convert Claude event to normalized TraceEvent.

        Claude Code emits events with different structure than Codex.
        This method maps Claude's format to our common TraceEvent model.
        """
        event_type = raw.get("type", "unknown")

        # Map Claude event types to our normalized types
        type_mapping = {
            "assistant": "item.completed",
            "tool_use": "item.started",
            "tool_result": "item.completed",
            "message": "turn.completed",
        }

        normalized_type = type_mapping.get(event_type, event_type)

        # Extract command from tool_use events
        command = None
        item_type = None
        if event_type == "tool_use":
            tool_name = raw.get("name", "")
            if tool_name == "bash":
                command = raw.get("input", {}).get("command")
                item_type = "command_execution"
            elif tool_name in ("read", "write", "edit"):
                item_type = "file_operation"
            else:
                item_type = tool_name

        # Extract output from tool_result events
        output = None
        if event_type == "tool_result":
            output = raw.get("content")
            item_type = "command_execution"

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
