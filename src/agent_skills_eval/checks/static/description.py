"""Description checks for skill descriptions."""

import re
from typing import ClassVar

from agent_skills_eval.checks.base import StaticCheck
from agent_skills_eval.core.models import CheckResult, EvalDimension, Severity, Skill
from agent_skills_eval.core.registry import register_check

# Maximum description length
MAX_DESCRIPTION_LENGTH = 1024

# Patterns that suggest first-person voice
FIRST_PERSON_PATTERNS = [
    r"\bI\s+(?:will|can|am|do|have)\b",
    r"\bI'm\b",
    r"\bI've\b",
    r"\bmy\b",
    r"\bme\b",
]

# Patterns that suggest trigger words are present
TRIGGER_PATTERNS = [
    r"\bwhen\b",
    r"\bif\b",
    r"\btrigger(?:s|ed)?\b",
    r"\bactivate(?:s|d)?\b",
    r"\binvoke(?:s|d)?\b",
    r"\buse(?:s|d)?\s+(?:when|for|to)\b",
]


@register_check
class DescriptionRequiredCheck(StaticCheck):
    """Check that description field is present."""

    check_id: ClassVar[str] = "description.required"
    check_name: ClassVar[str] = "Description Required"
    description: ClassVar[str] = "Description field is present in frontmatter"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.DESCRIPTION

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None:
            return self._fail(
                "No frontmatter found, cannot check description",
                location=str(skill.path / "SKILL.md"),
            )

        if "description" not in skill.metadata.raw:
            return self._fail(
                "Description field is missing from frontmatter",
                location=str(skill.path / "SKILL.md"),
            )

        return self._pass(
            "Description field present",
            location=str(skill.path / "SKILL.md"),
        )


@register_check
class DescriptionNotEmptyCheck(StaticCheck):
    """Check that description is not empty."""

    check_id: ClassVar[str] = "description.not-empty"
    check_name: ClassVar[str] = "Description Not Empty"
    description: ClassVar[str] = "Description is not empty or whitespace-only"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.DESCRIPTION

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None:
            return self._fail(
                "No frontmatter found",
                location=str(skill.path / "SKILL.md"),
            )

        desc = skill.metadata.description.strip()

        if not desc:
            return self._fail(
                "Description is empty or whitespace-only",
                location=str(skill.path / "SKILL.md"),
            )

        return self._pass(
            f"Description has content ({len(desc)} characters)",
            location=str(skill.path / "SKILL.md"),
        )


@register_check
class DescriptionMaxLengthCheck(StaticCheck):
    """Check that description doesn't exceed max length."""

    check_id: ClassVar[str] = "description.max-length"
    check_name: ClassVar[str] = "Description Max Length"
    description: ClassVar[str] = f"Description is under {MAX_DESCRIPTION_LENGTH} characters"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.DESCRIPTION

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None:
            return self._fail(
                "No frontmatter found",
                location=str(skill.path / "SKILL.md"),
            )

        desc = skill.metadata.description
        length = len(desc)

        if length > MAX_DESCRIPTION_LENGTH:
            return self._fail(
                f"Description exceeds {MAX_DESCRIPTION_LENGTH} characters (got {length})",
                details={"length": length, "max_length": MAX_DESCRIPTION_LENGTH},
                location=str(skill.path / "SKILL.md"),
            )

        return self._pass(
            f"Description length OK ({length}/{MAX_DESCRIPTION_LENGTH})",
            location=str(skill.path / "SKILL.md"),
        )


@register_check
class DescriptionThirdPersonCheck(StaticCheck):
    """Check that description uses third-person voice."""

    check_id: ClassVar[str] = "description.third-person"
    check_name: ClassVar[str] = "Third-Person Voice"
    description: ClassVar[str] = "Description uses third-person voice"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.DESCRIPTION

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None or not skill.metadata.description:
            return self._fail(
                "No description to check",
                location=str(skill.path / "SKILL.md"),
            )

        desc = skill.metadata.description
        found_first_person: list[str] = []

        for pattern in FIRST_PERSON_PATTERNS:
            matches = re.findall(pattern, desc, re.IGNORECASE)
            found_first_person.extend(matches)

        if found_first_person:
            return self._fail(
                "Description uses first-person voice",
                details={
                    "found": found_first_person[:5],  # Limit to first 5 matches
                    "suggestion": "Use third-person voice (e.g., 'Creates files...' instead of 'I create files...')",
                },
                location=str(skill.path / "SKILL.md"),
            )

        return self._pass(
            "Description uses appropriate voice",
            location=str(skill.path / "SKILL.md"),
        )


@register_check
class DescriptionIncludesTriggersCheck(StaticCheck):
    """Check that description includes trigger information."""

    check_id: ClassVar[str] = "description.includes-triggers"
    check_name: ClassVar[str] = "Includes Triggers"
    description: ClassVar[str] = "Description describes when to use the skill"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.DESCRIPTION

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None or not skill.metadata.description:
            return self._fail(
                "No description to check",
                location=str(skill.path / "SKILL.md"),
            )

        desc = skill.metadata.description.lower()

        for pattern in TRIGGER_PATTERNS:
            if re.search(pattern, desc, re.IGNORECASE):
                return self._pass(
                    "Description includes trigger information",
                    location=str(skill.path / "SKILL.md"),
                )

        return self._fail(
            "Description should describe when to use the skill",
            details={
                "suggestion": "Add context about when this skill should be triggered (e.g., 'Use when...', 'Activates if...')"
            },
            location=str(skill.path / "SKILL.md"),
        )
