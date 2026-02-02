"""Abstract base class for runtime adapters."""

import json
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

    Implementations should:
    1. Execute the skill with the given prompt
    2. Capture the execution trace
    3. Normalize trace events to the common TraceEvent format
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the runtime adapter name (e.g., 'codex', 'claude')."""
        ...

    @abstractmethod
    def execute(
        self,
        prompt: str,
        skill_path: Path,
        trace_path: Path,
        stop_on_skill: str | None = None,
    ) -> int:
        """Execute a skill with the given prompt and capture the trace.

        Args:
            prompt: The user prompt to send to the LLM.
            skill_path: Path to the skill directory.
            trace_path: Where to write the execution trace.
            stop_on_skill: If provided, terminate execution early when
                this skill is triggered. Used to optimize positive trigger
                tests by avoiding unnecessary API calls after detection.

        Returns:
            Exit code from the runtime (0 for success).
        """
        ...

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
        chunks = (
            content.split("\n\n")
            if "\n\n" in content
            else content.strip().split("\n")
        )

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                yield json.loads(chunk)
            except json.JSONDecodeError:
                continue
