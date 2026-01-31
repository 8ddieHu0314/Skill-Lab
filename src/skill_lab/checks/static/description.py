"""Description checks for skill descriptions."""

import re
from typing import ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import register_check

# Maximum description length
MAX_DESCRIPTION_LENGTH = 1024

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
    spec_required: ClassVar[bool] = True

    def run(self, skill: Skill) -> CheckResult:
        if fail := self._require_metadata(skill, "check description"):
            return fail
        assert skill.metadata is not None

        if "description" not in skill.metadata.raw:
            return self._fail(
                "Description field is missing from frontmatter",
                location=self._skill_md_location(skill),
            )

        return self._pass(
            "Description field present",
            location=self._skill_md_location(skill),
        )


@register_check
class DescriptionNotEmptyCheck(StaticCheck):
    """Check that description is not empty."""

    check_id: ClassVar[str] = "description.not-empty"
    check_name: ClassVar[str] = "Description Not Empty"
    description: ClassVar[str] = "Description is not empty or whitespace-only"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.DESCRIPTION
    spec_required: ClassVar[bool] = True

    def run(self, skill: Skill) -> CheckResult:
        if fail := self._require_metadata(skill):
            return fail
        assert skill.metadata is not None

        desc = skill.metadata.description.strip()

        if not desc:
            return self._fail(
                "Description is empty or whitespace-only",
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"Description has content ({len(desc)} characters)",
            location=self._skill_md_location(skill),
        )


@register_check
class DescriptionMaxLengthCheck(StaticCheck):
    """Check that description doesn't exceed max length."""

    check_id: ClassVar[str] = "description.max-length"
    check_name: ClassVar[str] = "Description Max Length"
    description: ClassVar[str] = f"Description is under {MAX_DESCRIPTION_LENGTH} characters"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.DESCRIPTION
    spec_required: ClassVar[bool] = True

    def run(self, skill: Skill) -> CheckResult:
        if fail := self._require_metadata(skill):
            return fail
        assert skill.metadata is not None

        desc = skill.metadata.description
        length = len(desc)

        if length > MAX_DESCRIPTION_LENGTH:
            return self._fail(
                f"Description exceeds {MAX_DESCRIPTION_LENGTH} characters (got {length})",
                details={"length": length, "max_length": MAX_DESCRIPTION_LENGTH},
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"Description length OK ({length}/{MAX_DESCRIPTION_LENGTH})",
            location=self._skill_md_location(skill),
        )


@register_check
class DescriptionIncludesTriggersCheck(StaticCheck):
    """Check that description includes trigger information (spec recommendation)."""

    check_id: ClassVar[str] = "description.includes-triggers"
    check_name: ClassVar[str] = "Includes Triggers"
    description: ClassVar[str] = "Description describes when to use the skill"
    severity: ClassVar[Severity] = Severity.INFO
    dimension: ClassVar[EvalDimension] = EvalDimension.DESCRIPTION

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None or not skill.metadata.description:
            return self._fail(
                "No description to check",
                location=self._skill_md_location(skill),
            )

        desc = skill.metadata.description.lower()

        for pattern in TRIGGER_PATTERNS:
            if re.search(pattern, desc, re.IGNORECASE):
                return self._pass(
                    "Description includes trigger information",
                    location=self._skill_md_location(skill),
                )

        return self._fail(
            "Description should describe when to use the skill",
            details={
                "suggestion": "Add context about when this skill should be triggered (e.g., 'Use when...', 'Activates if...')"
            },
            location=self._skill_md_location(skill),
        )
