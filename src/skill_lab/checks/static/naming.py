"""Naming checks for skill names and identifiers."""

import re
from typing import ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import register_check

# Name format: lowercase letters, numbers, and hyphens only
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$")

# Maximum name length
MAX_NAME_LENGTH = 64

@register_check
class NameRequiredCheck(StaticCheck):
    """Check that name field is present."""

    check_id: ClassVar[str] = "naming.required"
    check_name: ClassVar[str] = "Name Required"
    description: ClassVar[str] = "Name field is present in frontmatter"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.NAMING
    spec_required: ClassVar[bool] = True

    def run(self, skill: Skill) -> CheckResult:
        if fail := self._require_metadata(skill, "check name"):
            return fail
        assert skill.metadata is not None

        if not skill.metadata.name:
            return self._fail(
                "Name field is missing or empty in frontmatter",
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"Name field present: '{skill.metadata.name}'",
            location=self._skill_md_location(skill),
        )


@register_check
class NameFormatCheck(StaticCheck):
    """Check that name follows format rules."""

    check_id: ClassVar[str] = "naming.format"
    check_name: ClassVar[str] = "Name Format"
    description: ClassVar[str] = "Name is lowercase, hyphen-separated, max 64 chars"
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
        errors: list[str] = []

        # Check length
        if len(name) > MAX_NAME_LENGTH:
            errors.append(f"Name exceeds {MAX_NAME_LENGTH} characters (got {len(name)})")

        # Check format
        if not NAME_PATTERN.match(name):
            errors.append(
                "Name must be lowercase letters, numbers, and hyphens only, "
                "starting with a letter"
            )

        # Check for consecutive hyphens
        if "--" in name:
            errors.append("Name should not contain consecutive hyphens")

        if errors:
            return self._fail(
                "; ".join(errors),
                details={"name": name, "errors": errors},
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"Name '{name}' follows format rules",
            location=self._skill_md_location(skill),
        )


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


