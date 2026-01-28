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

# Reserved words that should not appear in skill names (quality suggestion, not in spec)
RESERVED_WORDS = {"anthropic", "claude", "openai", "gpt"}

# Common gerund prefixes
GERUND_PREFIXES = {
    "creating",
    "building",
    "managing",
    "handling",
    "processing",
    "generating",
    "analyzing",
    "converting",
    "formatting",
    "validating",
    "testing",
    "deploying",
    "configuring",
    "monitoring",
    "debugging",
    "optimizing",
    "implementing",
    "developing",
    "writing",
    "reading",
    "updating",
    "deleting",
    "searching",
    "filtering",
    "sorting",
    "parsing",
    "rendering",
    "fetching",
    "sending",
    "receiving",
    "authenticating",
    "authorizing",
}


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


@register_check
class NoReservedWordsCheck(StaticCheck):
    """Check that name doesn't contain reserved words (quality suggestion)."""

    check_id: ClassVar[str] = "naming.no-reserved"
    check_name: ClassVar[str] = "No Reserved Words"
    description: ClassVar[str] = "Name does not contain 'anthropic', 'claude', etc."
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.NAMING

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None or not skill.metadata.name:
            return self._fail(
                "No name to validate",
                location=self._skill_md_location(skill),
            )

        name = skill.metadata.name.lower()
        found_reserved: list[str] = []

        for word in RESERVED_WORDS:
            if word in name:
                found_reserved.append(word)

        if found_reserved:
            return self._fail(
                f"Name contains reserved words: {', '.join(found_reserved)}",
                details={"name": skill.metadata.name, "reserved_words": found_reserved},
                location=self._skill_md_location(skill),
            )

        return self._pass(
            "Name does not contain reserved words",
            location=self._skill_md_location(skill),
        )


@register_check
class GerundConventionCheck(StaticCheck):
    """Check that name uses gerund form (quality suggestion, not in spec)."""

    check_id: ClassVar[str] = "naming.gerund-convention"
    check_name: ClassVar[str] = "Gerund Naming"
    description: ClassVar[str] = "Name uses gerund form (e.g., 'creating-docs')"
    severity: ClassVar[Severity] = Severity.INFO
    dimension: ClassVar[EvalDimension] = EvalDimension.NAMING

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None or not skill.metadata.name:
            return self._fail(
                "No name to validate",
                location=self._skill_md_location(skill),
            )

        name = skill.metadata.name.lower()

        # Check if name starts with a gerund prefix
        for prefix in GERUND_PREFIXES:
            if name.startswith(prefix):
                return self._pass(
                    f"Name uses gerund form (starts with '{prefix}')",
                    location=self._skill_md_location(skill),
                )

        # Check if first word ends in -ing
        first_word = name.split("-")[0]
        if first_word.endswith("ing"):
            return self._pass(
                f"Name uses gerund form ('{first_word}' ends in -ing)",
                location=self._skill_md_location(skill),
            )

        return self._fail(
            "Skill name should use gerund form (e.g., 'creating-docs', 'managing-tasks')",
            details={"name": skill.metadata.name, "suggestion": "Consider renaming to start with a verb ending in -ing"},
            location=self._skill_md_location(skill),
        )
