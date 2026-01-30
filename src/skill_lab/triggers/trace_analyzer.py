"""Analyze execution traces for skill invocations and command patterns."""

from collections import Counter
from pathlib import Path

from skill_lab.core.models import TraceEvent


class TraceAnalyzer:
    """Analyze execution traces for deterministic checks.

    This analyzer examines normalized TraceEvent lists to determine:
    - Whether a skill was triggered
    - Which commands were executed
    - File operations performed
    - Loop/thrashing detection
    """

    def __init__(self, events: list[TraceEvent]) -> None:
        """Initialize with a list of trace events.

        Args:
            events: List of normalized TraceEvent objects.
        """
        self.events = events

    def skill_was_triggered(self, skill_name: str) -> bool:
        """Check if a specific skill was invoked.

        Looks for skill invocation events or commands that reference
        the skill name.

        Args:
            skill_name: Name of the skill to check for.

        Returns:
            True if the skill appears to have been triggered.
        """
        for event in self.events:
            # Check for explicit skill invocation events
            if event.item_type == "skill_invocation" and skill_name in (event.command or ""):
                return True

            # Check for skill references in commands
            if event.command and skill_name in event.command:
                return True

            # Check raw event data for skill references
            raw_str = str(event.raw)
            if f"${skill_name}" in raw_str or f"skill:{skill_name}" in raw_str:
                return True

        return False

    def command_was_run(self, pattern: str) -> bool:
        """Check if a command matching the pattern was executed.

        Args:
            pattern: Substring to search for in commands.

        Returns:
            True if a matching command was found.
        """
        return any(
            event.command and pattern in event.command
            for event in self.events
            if event.type in ("item.started", "item.completed")
            and event.item_type == "command_execution"
        )

    def file_was_created(self, filepath: str, project_dir: Path) -> bool:
        """Check if a file exists after execution.

        Args:
            filepath: Relative path to check.
            project_dir: Base directory for relative path resolution.

        Returns:
            True if the file exists.
        """
        return (project_dir / filepath).exists()

    def get_command_sequence(self) -> list[str]:
        """Extract ordered list of commands that were run.

        Returns:
            List of command strings in execution order.
        """
        return [
            event.command
            for event in self.events
            if event.type == "item.completed"
            and event.item_type == "command_execution"
            and event.command
        ]

    def detect_loops(self, max_repeats: int = 3) -> bool:
        """Detect if the same command was repeated too many times.

        This helps identify thrashing or infinite loops in agent behavior.

        Args:
            max_repeats: Maximum allowed repetitions before flagging.

        Returns:
            True if excessive repetition was detected.
        """
        commands = self.get_command_sequence()
        counts = Counter(commands)
        return any(count > max_repeats for count in counts.values())

    def get_all_commands_matching(self, patterns: list[str]) -> list[str]:
        """Get all commands that match any of the given patterns.

        Args:
            patterns: List of substrings to match.

        Returns:
            List of matching commands.
        """
        matching: list[str] = []
        for event in self.events:
            if event.command:
                for pattern in patterns:
                    if pattern in event.command:
                        matching.append(event.command)
                        break
        return matching

    def has_errors(self) -> bool:
        """Check if any error events occurred in the trace.

        Returns:
            True if error events are present.
        """
        return any(event.type == "error" for event in self.events)

    def get_error_messages(self) -> list[str]:
        """Extract error messages from the trace.

        Returns:
            List of error messages found.
        """
        errors: list[str] = []
        for event in self.events:
            if event.type == "error":
                msg = event.raw.get("message", "Unknown error")
                errors.append(msg)
        return errors

    def count_events_by_type(self) -> dict[str, int]:
        """Count events grouped by type.

        Returns:
            Dictionary mapping event types to counts.
        """
        counts: dict[str, int] = {}
        for event in self.events:
            counts[event.type] = counts.get(event.type, 0) + 1
        return counts
