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
        """Parse Claude trace into normalized TraceEvent objects.

        Filters out stream_event types (text streaming deltas) as they
        are not useful for trace analysis - we only care about tool
        invocations and results.
        """
        if not trace_path.exists():
            return

        content = trace_path.read_text()
        for line in content.strip().split("\n"):
            if not line:
                continue
            try:
                raw = json.loads(line)
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
