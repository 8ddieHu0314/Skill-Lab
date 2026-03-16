"""Codex CLI runtime adapter for executing skills."""

import json
import shutil
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

    def _cli_binary_name(self) -> str:
        return "codex"

    def _build_command(self, cli_path: str, prompt: str) -> list[str]:
        return [
            cli_path,
            "exec",
            "--json",  # REQUIRED: emit structured events
            "--full-auto",  # Allow file system changes
            prompt,
        ]

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
        if item.get("type") == "skill_invocation" and skill_name in (item.get("command") or ""):
            return True

        # Check for explicit $skill-name or skill:skill-name patterns
        raw_str = str(event)
        return f"${skill_name}" in raw_str or f"skill:{skill_name}" in raw_str

    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]:
        """Parse Codex trace into normalized TraceEvent objects."""
        for raw in self._parse_trace_chunks(trace_path):
            yield self._normalize_event(raw)

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
