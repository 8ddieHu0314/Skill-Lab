"""Base class for static checks."""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill


class StaticCheck(ABC):
    """Base class for all static checks.

    Subclasses must define class-level attributes and implement the run() method.
    """

    # These must be overridden by subclasses
    check_id: ClassVar[str]
    check_name: ClassVar[str]
    description: ClassVar[str]
    severity: ClassVar[Severity]
    dimension: ClassVar[EvalDimension]

    # Whether this check is required by the Agent Skills spec (default: False = quality suggestion)
    spec_required: ClassVar[bool] = False

    @abstractmethod
    def run(self, skill: Skill) -> CheckResult:
        """Execute the check against a skill.

        Args:
            skill: The parsed skill to check.

        Returns:
            CheckResult with pass/fail status and details.
        """
        pass

    def _skill_md_location(self, skill: Skill) -> str:
        """Get the standard location string for SKILL.md.

        Args:
            skill: The skill being checked.

        Returns:
            Path string to SKILL.md.
        """
        return str(skill.path / "SKILL.md")

    def _require_metadata(
        self, skill: Skill, context: str = "perform this check"
    ) -> CheckResult | None:
        """Check that skill has metadata, returning a failure result if not.

        Args:
            skill: The skill to check.
            context: Description of what requires metadata (for error message).

        Returns:
            None if metadata exists, or a failing CheckResult if not.
        """
        if skill.metadata is None:
            return self._fail(
                f"No frontmatter found, cannot {context}",
                location=self._skill_md_location(skill),
            )
        return None

    def _pass(self, message: str, **kwargs: Any) -> CheckResult:
        """Create a passing CheckResult.

        Args:
            message: Success message.
            **kwargs: Additional fields (details, location).

        Returns:
            CheckResult with passed=True.
        """
        return CheckResult(
            check_id=self.check_id,
            check_name=self.check_name,
            passed=True,
            severity=self.severity,
            dimension=self.dimension,
            message=message,
            details=kwargs.get("details"),
            location=kwargs.get("location"),
        )

    def _fail(self, message: str, **kwargs: Any) -> CheckResult:
        """Create a failing CheckResult.

        Args:
            message: Failure message.
            **kwargs: Additional fields (details, location).

        Returns:
            CheckResult with passed=False.
        """
        return CheckResult(
            check_id=self.check_id,
            check_name=self.check_name,
            passed=False,
            severity=self.severity,
            dimension=self.dimension,
            message=message,
            details=kwargs.get("details"),
            location=kwargs.get("location"),
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.check_id}>"
