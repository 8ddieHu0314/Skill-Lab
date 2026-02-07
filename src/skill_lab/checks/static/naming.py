"""Naming checks for skill names and identifiers."""

from typing import ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import register_check


@register_check
class NameMatchesDirectoryCheck(StaticCheck):
    """Check that name matches the parent directory name (spec requirement)."""

    check_id: ClassVar[str] = "naming.matches-directory"
    check_name: ClassVar[str] = "Name Matches Directory"
    description: ClassVar[str] = "Name must match the parent directory name"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.NAMING
    spec_required: ClassVar[bool] = True

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None or not skill.metadata.name:
            return self._fail(
                "No name to validate",
                location=self._skill_md_location(skill),
            )

        name = skill.metadata.name
        directory_name = skill.path.name

        if name != directory_name:
            return self._fail(
                f"Name '{name}' does not match directory name '{directory_name}'",
                details={"name": name, "directory": directory_name},
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"Name '{name}' matches directory name",
            location=self._skill_md_location(skill),
        )
