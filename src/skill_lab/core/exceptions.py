"""Custom exception hierarchy for skill-lab.

Provides structured exceptions with actionable error messages and context.
"""

from typing import Any


class SkillLabError(Exception):
    """Base exception for all skill-lab errors.

    Provides a consistent interface for error handling with:
    - User-friendly message
    - Optional context dictionary for debugging
    - Optional suggestion for how to fix the issue
    """

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ) -> None:
        """Initialize the error.

        Args:
            message: User-friendly error message.
            context: Optional dictionary with debugging context.
            suggestion: Optional suggestion for how to resolve the issue.
        """
        self.message = message
        self.context = context or {}
        self.suggestion = suggestion
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the complete error message."""
        parts = [self.message]
        if self.suggestion:
            parts.append(f"Suggestion: {self.suggestion}")
        return " | ".join(parts)


class ParseError(SkillLabError):
    """Error parsing skill files or configuration.

    Raised when SKILL.md, YAML frontmatter, or test files cannot be parsed.
    """

    def __init__(
        self,
        message: str,
        *,
        file_path: str | None = None,
        line_number: int | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ) -> None:
        """Initialize the parse error.

        Args:
            message: Description of the parse error.
            file_path: Path to the file that failed to parse.
            line_number: Line number where the error occurred.
            context: Additional context for debugging.
            suggestion: How to fix the parsing issue.
        """
        self.file_path = file_path
        self.line_number = line_number
        ctx = context or {}
        if file_path:
            ctx["file_path"] = file_path
        if line_number:
            ctx["line_number"] = line_number
        super().__init__(message, context=ctx, suggestion=suggestion)


class CheckExecutionError(SkillLabError):
    """Error during check execution.

    Raised when a check fails to execute (not when it fails its assertion).
    """

    def __init__(
        self,
        message: str,
        *,
        check_id: str | None = None,
        check_name: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ) -> None:
        """Initialize the check execution error.

        Args:
            message: Description of what went wrong.
            check_id: ID of the check that failed.
            check_name: Name of the check that failed.
            context: Additional context for debugging.
            suggestion: How to fix the issue.
        """
        self.check_id = check_id
        self.check_name = check_name
        ctx = context or {}
        if check_id:
            ctx["check_id"] = check_id
        if check_name:
            ctx["check_name"] = check_name
        super().__init__(message, context=ctx, suggestion=suggestion)


class TraceParseError(ParseError):
    """Error parsing execution trace files.

    Raised when JSONL trace files are malformed or contain invalid events.
    """

    def __init__(
        self,
        message: str,
        *,
        file_path: str | None = None,
        line_number: int | None = None,
        event_type: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ) -> None:
        """Initialize the trace parse error.

        Args:
            message: Description of the parse error.
            file_path: Path to the trace file.
            line_number: Line number in the trace file.
            event_type: Type of event that failed to parse.
            context: Additional context for debugging.
            suggestion: How to fix the issue.
        """
        self.event_type = event_type
        ctx = context or {}
        if event_type:
            ctx["event_type"] = event_type
        super().__init__(
            message,
            file_path=file_path,
            line_number=line_number,
            context=ctx,
            suggestion=suggestion,
        )


class ConfigurationError(SkillLabError):
    """Error in skill-lab configuration.

    Raised when configuration files or options are invalid.
    """

    pass


class RuntimeError(SkillLabError):
    """Error during runtime execution.

    Raised when the runtime (Codex, Claude) fails to execute a prompt.
    """

    def __init__(
        self,
        message: str,
        *,
        runtime_name: str | None = None,
        exit_code: int | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ) -> None:
        """Initialize the runtime error.

        Args:
            message: Description of what went wrong.
            runtime_name: Name of the runtime that failed.
            exit_code: Exit code from the runtime.
            context: Additional context for debugging.
            suggestion: How to fix the issue.
        """
        self.runtime_name = runtime_name
        self.exit_code = exit_code
        ctx = context or {}
        if runtime_name:
            ctx["runtime_name"] = runtime_name
        if exit_code is not None:
            ctx["exit_code"] = exit_code
        super().__init__(message, context=ctx, suggestion=suggestion)


class ValidationError(SkillLabError):
    """Error validating skill structure or content.

    Raised when required files are missing or invalid.
    """

    def __init__(
        self,
        message: str,
        *,
        skill_path: str | None = None,
        missing_items: list[str] | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ) -> None:
        """Initialize the validation error.

        Args:
            message: Description of what's invalid.
            skill_path: Path to the skill being validated.
            missing_items: List of missing required items.
            context: Additional context for debugging.
            suggestion: How to fix the issue.
        """
        self.skill_path = skill_path
        self.missing_items = missing_items or []
        ctx = context or {}
        if skill_path:
            ctx["skill_path"] = skill_path
        if missing_items:
            ctx["missing_items"] = missing_items
        super().__init__(message, context=ctx, suggestion=suggestion)
