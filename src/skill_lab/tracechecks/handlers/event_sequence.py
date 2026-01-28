"""Handler for event_sequence trace checks."""

from pathlib import Path

from skill_lab.core.models import TraceCheckDefinition, TraceCheckResult
from skill_lab.tracechecks.handlers.base import TraceCheckHandler
from skill_lab.tracechecks.registry import register_trace_handler
from skill_lab.triggers.trace_analyzer import TraceAnalyzer


@register_trace_handler("event_sequence")
class EventSequenceHandler(TraceCheckHandler):
    """Check if commands were executed in the correct order.

    YAML format:
        - id: correct-sequence
          type: event_sequence
          sequence: ["npm init", "npm install", "npm run build"]
    """

    def run(
        self,
        check: TraceCheckDefinition,
        analyzer: TraceAnalyzer,
        project_dir: Path,
    ) -> TraceCheckResult:
        """Check if commands matching the sequence appeared in order.

        The sequence patterns don't need to be consecutive, just in order.
        For example, sequence ["a", "b", "c"] would pass for commands
        ["a", "x", "b", "y", "z", "c"].

        Args:
            check: Check definition with sequence field.
            analyzer: TraceAnalyzer with parsed trace events.
            project_dir: Project directory (unused for this check).

        Returns:
            TraceCheckResult indicating if sequence was found.
        """
        sequence = self._require_field(check, "sequence")
        if isinstance(sequence, TraceCheckResult):
            return sequence

        commands = analyzer.get_command_sequence()

        # Find each pattern in order
        found_indices: list[int] = []
        found_commands: list[str] = []
        search_start = 0

        for pattern in sequence:
            found = False
            for i in range(search_start, len(commands)):
                if pattern in commands[i]:
                    found_indices.append(i)
                    found_commands.append(commands[i])
                    search_start = i + 1
                    found = True
                    break

            if not found:
                missing_patterns = list(sequence[len(found_indices) :])
                return self._fail(
                    check,
                    f"Sequence incomplete: missing '{pattern}'",
                    {
                        "expected_sequence": list(sequence),
                        "found_patterns": found_commands,
                        "missing_patterns": missing_patterns,
                        "commands_executed": commands[:20],  # Limit for readability
                    },
                )

        return self._pass(
            check,
            f"All {len(sequence)} commands found in correct order",
            {
                "expected_sequence": list(sequence),
                "found_commands": found_commands,
                "indices": found_indices,
            },
        )
