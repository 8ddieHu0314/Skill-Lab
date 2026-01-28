"""Base class for trace check handlers."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from skill_lab.core.models import TraceCheckDefinition, TraceCheckResult
from skill_lab.triggers.trace_analyzer import TraceAnalyzer


class TraceCheckHandler(ABC):
    """Abstract base class for trace check handlers.

    Each handler implements a specific check type (e.g., command_presence,
    file_creation). Handlers are registered with the trace registry and
    invoked by the trace evaluator based on the check type in YAML definitions.
    """

    @abstractmethod
    def run(
        self,
        check: TraceCheckDefinition,
        analyzer: TraceAnalyzer,
        project_dir: Path,
    ) -> TraceCheckResult:
        """Execute the check against a trace.

        Args:
            check: The check definition from YAML.
            analyzer: TraceAnalyzer with parsed trace events.
            project_dir: Path to the project directory (for file checks).

        Returns:
            TraceCheckResult indicating pass/fail and details.
        """
        pass

    def _require_field(
        self, check: TraceCheckDefinition, field_name: str
    ) -> TraceCheckResult | Any:
        """Get a required field from the check definition, or return failure result.

        Args:
            check: The check definition.
            field_name: Name of the required field.

        Returns:
            The field value if present and non-empty, or a failing TraceCheckResult.
        """
        value = getattr(check, field_name, None)
        if not value:
            return self._fail(check, f"Missing required '{field_name}' field")
        return value

    def _pass(self, check: TraceCheckDefinition, message: str, details: dict[str, object] | None = None) -> TraceCheckResult:
        """Create a passing result.

        Args:
            check: The check definition.
            message: Success message.
            details: Optional additional details.

        Returns:
            TraceCheckResult with passed=True.
        """
        return TraceCheckResult(
            check_id=check.id,
            check_type=check.type,
            passed=True,
            message=message,
            details=details,
        )

    def _fail(self, check: TraceCheckDefinition, message: str, details: dict[str, object] | None = None) -> TraceCheckResult:
        """Create a failing result.

        Args:
            check: The check definition.
            message: Failure message.
            details: Optional additional details.

        Returns:
            TraceCheckResult with passed=False.
        """
        return TraceCheckResult(
            check_id=check.id,
            check_type=check.type,
            passed=False,
            message=message,
            details=details,
        )
