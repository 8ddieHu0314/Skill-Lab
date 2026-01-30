"""Abstract base class for runtime adapters."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

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
    ) -> int:
        """Execute a skill with the given prompt and capture the trace.

        Args:
            prompt: The user prompt to send to the LLM.
            skill_path: Path to the skill directory.
            trace_path: Where to write the execution trace.

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
