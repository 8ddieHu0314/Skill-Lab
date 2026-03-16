"""Claude Code runtime adapter for executing skills."""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from skill_lab.core.constants import skill_script_patterns
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

    def _cli_binary_name(self) -> str:
        return "claude"

    def _build_command(self, cli_path: str, prompt: str) -> list[str]:
        return [
            cli_path,
            "--print",  # Output mode
            "--verbose",  # Required for stream-json output
            "--output-format",
            "stream-json",
            "-p",
            prompt,
        ]

    def _check_skill_trigger(self, line: str, skill_name: str) -> bool:
        """Check if a JSONL line indicates the skill was triggered.

        Looks for:
        1. Skill tool invocations with the specified skill name
        2. Bash commands referencing the skill's scripts
        3. Read operations on skill files

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

        # Patterns that indicate skill execution
        skill_patterns = skill_script_patterns(skill_name)

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
                    if not isinstance(item, dict):
                        continue
                    tool_name = item.get("name")
                    tool_input = item.get("input", {})

                    # Check for Skill tool
                    if (
                        tool_name == "Skill"
                        and isinstance(tool_input, dict)
                        and tool_input.get("skill") == skill_name
                    ):
                        return True

                    # Check for Bash tool running skill scripts
                    if tool_name == "Bash" and isinstance(tool_input, dict):
                        command = tool_input.get("command", "")
                        if any(pattern in command for pattern in skill_patterns):
                            return True

                    # Check for Read tool accessing skill files
                    if tool_name == "Read" and isinstance(tool_input, dict):
                        file_path = tool_input.get("file_path", "")
                        if any(pattern in file_path for pattern in skill_patterns):
                            return True

        return False

    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]:
        """Parse Claude trace into normalized TraceEvent objects.

        Filters out stream_event types (text streaming deltas) as they
        are not useful for trace analysis - we only care about tool
        invocations and results.
        """
        for raw in self._parse_trace_chunks(trace_path):
            # Skip stream events (text deltas) - not useful for analysis
            if raw.get("type") == "stream_event":
                continue
            yield self._normalize_event(raw)

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
