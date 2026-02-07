"""Description checks for skill descriptions."""

import re
from typing import ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import register_check

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
