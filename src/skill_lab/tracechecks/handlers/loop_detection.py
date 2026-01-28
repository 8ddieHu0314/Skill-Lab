"""Handler for loop_detection trace checks."""

from collections import Counter
from pathlib import Path

from skill_lab.core.models import TraceCheckDefinition, TraceCheckResult
from skill_lab.tracechecks.handlers.base import TraceCheckHandler
from skill_lab.tracechecks.registry import register_trace_handler
from skill_lab.triggers.trace_analyzer import TraceAnalyzer


@register_trace_handler("loop_detection")
class LoopDetectionHandler(TraceCheckHandler):
    """Detect excessive command repetition (thrashing).

    YAML format:
        - id: no-excessive-retries
          type: loop_detection
          max_retries: 3
    """

    def run(
        self,
        check: TraceCheckDefinition,
        analyzer: TraceAnalyzer,
        project_dir: Path,
    ) -> TraceCheckResult:
        """Check if any command was repeated more than max_retries times.

        Args:
            check: Check definition with max_retries field.
            analyzer: TraceAnalyzer with parsed trace events.
            project_dir: Project directory (unused for this check).

        Returns:
            TraceCheckResult indicating if loops were detected.
        """
        max_retries = check.max_retries

        commands = analyzer.get_command_sequence()
        counts = Counter(commands)

        # Find commands that exceed the limit
        violations: list[tuple[str, int]] = []
        for cmd, count in counts.items():
            if count > max_retries:
                violations.append((cmd, count))

        if violations:
            # Sort by count descending
            violations.sort(key=lambda x: x[1], reverse=True)
            worst_cmd, worst_count = violations[0]
            return self._fail(
                check,
                f"Command repeated {worst_count} times (max: {max_retries}): {worst_cmd[:50]}...",
                {
                    "max_retries": max_retries,
                    "violations": [{"command": cmd, "count": cnt} for cmd, cnt in violations[:5]],
                    "total_commands": len(commands),
                },
            )
        else:
            return self._pass(
                check,
                f"No command repeated more than {max_retries} times",
                {"max_retries": max_retries, "total_commands": len(commands)},
            )
