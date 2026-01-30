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
    ) -> int:
        """Run Codex with the given prompt, capturing structured events.

        Args:
            prompt: The user prompt to send.
            skill_path: Path to the skill directory.
            trace_path: Where to write the JSONL trace.

        Returns:
            Exit code from Codex.
        """
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                [
                    "codex",
                    "exec",
                    "--json",  # REQUIRED: emit structured events
                    "--full-auto",  # Allow file system changes
                    prompt,
                ],
                capture_output=True,
                text=True,
                cwd=skill_path,
                timeout=300,  # 5 minute timeout
            )

            # stdout is JSONL when --json is enabled
            trace_path.write_text(result.stdout)

            return result.returncode

        except subprocess.TimeoutExpired:
            trace_path.write_text('{"type": "error", "message": "Execution timed out"}\n')
            return 124  # Standard timeout exit code

        except FileNotFoundError:
            trace_path.write_text(
                '{"type": "error", "message": "Codex CLI not found"}\n'
            )
            return 127  # Command not found exit code

    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]:
        """Parse JSONL trace into normalized TraceEvent objects."""
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
