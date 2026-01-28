"""Handler for efficiency trace checks."""

from pathlib import Path

from skill_lab.core.models import TraceCheckDefinition, TraceCheckResult
from skill_lab.tracechecks.handlers.base import TraceCheckHandler
from skill_lab.tracechecks.registry import register_trace_handler
from skill_lab.triggers.trace_analyzer import TraceAnalyzer


@register_trace_handler("efficiency")
class EfficiencyHandler(TraceCheckHandler):
    """Check execution efficiency (command count limits).

    YAML format:
        - id: command-count-limit
          type: efficiency
          max_commands: 20
    """

    def run(
        self,
        check: TraceCheckDefinition,
        analyzer: TraceAnalyzer,
        project_dir: Path,
    ) -> TraceCheckResult:
        """Check if execution stayed within efficiency limits.

        Args:
            check: Check definition with max_commands field.
            analyzer: TraceAnalyzer with parsed trace events.
            project_dir: Project directory (unused for this check).

        Returns:
            TraceCheckResult indicating if limits were exceeded.
        """
        # Note: max_commands can be 0, so we check for None explicitly
        if check.max_commands is None:
            return self._fail(check, "Missing required 'max_commands' field")
        max_commands = check.max_commands

        commands = analyzer.get_command_sequence()
        command_count = len(commands)

        if command_count <= max_commands:
            return self._pass(
                check,
                f"Execution used {command_count} commands (limit: {max_commands})",
                {"command_count": command_count, "max_commands": max_commands},
            )
        else:
            return self._fail(
                check,
                f"Execution used {command_count} commands, exceeding limit of {max_commands}",
                {
                    "command_count": command_count,
                    "max_commands": max_commands,
                    "excess": command_count - max_commands,
                },
            )
