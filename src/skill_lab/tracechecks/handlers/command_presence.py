"""Handler for command_presence trace checks."""

from pathlib import Path

from skill_lab.core.models import TraceCheckDefinition, TraceCheckResult
from skill_lab.tracechecks.handlers.base import TraceCheckHandler
from skill_lab.tracechecks.registry import register_trace_handler
from skill_lab.triggers.trace_analyzer import TraceAnalyzer


@register_trace_handler("command_presence")
class CommandPresenceHandler(TraceCheckHandler):
    """Check if a command matching a pattern was executed.

    YAML format:
        - id: npm-install-ran
          type: command_presence
          pattern: "npm install"
    """

    def run(
        self,
        check: TraceCheckDefinition,
        analyzer: TraceAnalyzer,
        project_dir: Path,
    ) -> TraceCheckResult:
        """Check if a command matching the pattern was executed.

        Args:
            check: Check definition with pattern field.
            analyzer: TraceAnalyzer with parsed trace events.
            project_dir: Project directory (unused for this check).

        Returns:
            TraceCheckResult indicating if pattern was found.
        """
        pattern = self._require_field(check, "pattern")
        if isinstance(pattern, TraceCheckResult):
            return pattern

        if analyzer.command_was_run(pattern):
            return self._pass(
                check,
                f"Command matching '{pattern}' was executed",
                {"pattern": pattern},
            )
        else:
            commands = analyzer.get_command_sequence()
            return self._fail(
                check,
                f"No command matching '{pattern}' was found in trace",
                {"pattern": pattern, "commands_executed": commands[:10]},  # Limit for readability
            )
