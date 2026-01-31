"""Content checks for SKILL.md body and quality."""

import re
from pathlib import Path
from typing import ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import register_check

# Maximum line count for skill body
MAX_LINE_COUNT = 500

# Patterns that indicate code examples
CODE_EXAMPLE_PATTERNS = [
    r"```",  # Fenced code blocks
    r"^\s{4,}\S",  # Indented code blocks
    r"<example>",  # Example tags
]

# Maximum nesting depth for references
MAX_REFERENCE_DEPTH = 1


@register_check
class BodyNotEmptyCheck(StaticCheck):
    """Check that SKILL.md body has content (quality suggestion, spec allows empty body)."""

    check_id: ClassVar[str] = "content.body-not-empty"
    check_name: ClassVar[str] = "Body Not Empty"
    description: ClassVar[str] = "SKILL.md body has meaningful content"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        body = skill.body.strip()

        if not body:
            return self._fail(
                "SKILL.md body is empty",
                location=self._skill_md_location(skill),
            )

        # Check for minimal content (at least 50 characters of actual content)
        if len(body) < 50:
            return self._fail(
                f"SKILL.md body is too short ({len(body)} characters)",
                details={"length": len(body), "minimum": 50},
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"SKILL.md body has content ({len(body)} characters)",
            location=self._skill_md_location(skill),
        )


@register_check
class LineBudgetCheck(StaticCheck):
    """Check that body is under line budget."""

    check_id: ClassVar[str] = "content.line-budget"
    check_name: ClassVar[str] = "Line Budget"
    description: ClassVar[str] = f"Body is under {MAX_LINE_COUNT} lines"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        lines = skill.body.split("\n")
        line_count = len(lines)

        if line_count > MAX_LINE_COUNT:
            return self._fail(
                f"Body exceeds {MAX_LINE_COUNT} lines (got {line_count})",
                details={"line_count": line_count, "max_lines": MAX_LINE_COUNT},
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"Body within line budget ({line_count}/{MAX_LINE_COUNT})",
            location=self._skill_md_location(skill),
        )


@register_check
class HasExamplesCheck(StaticCheck):
    """Check that content contains code examples."""

    check_id: ClassVar[str] = "content.has-examples"
    check_name: ClassVar[str] = "Has Examples"
    description: ClassVar[str] = "Content contains code examples"
    severity: ClassVar[Severity] = Severity.INFO
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        body = skill.body

        for pattern in CODE_EXAMPLE_PATTERNS:
            if re.search(pattern, body, re.MULTILINE):
                return self._pass(
                    "Content contains code examples",
                    location=self._skill_md_location(skill),
                )

        return self._fail(
            "Content does not contain code examples",
            details={"suggestion": "Add code examples using fenced code blocks (```)"},
            location=self._skill_md_location(skill),
        )


@register_check
class ReferenceDepthCheck(StaticCheck):
    """Check that references are not too deeply nested."""

    check_id: ClassVar[str] = "content.reference-depth"
    check_name: ClassVar[str] = "Reference Depth"
    description: ClassVar[str] = f"References are max {MAX_REFERENCE_DEPTH} level deep"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        references_path = skill.path / "references"

        if not references_path.exists() or not references_path.is_dir():
            return self._pass(
                "No references folder to check",
            )

        deep_paths: list[str] = []

        def check_depth(path: Path, current_depth: int) -> None:
            if current_depth > MAX_REFERENCE_DEPTH:
                deep_paths.append(str(path.relative_to(skill.path)))
                return

            if path.is_dir():
                for item in path.iterdir():
                    if item.is_dir():
                        check_depth(item, current_depth + 1)

        check_depth(references_path, 0)

        if deep_paths:
            return self._fail(
                f"References nested too deeply (max {MAX_REFERENCE_DEPTH} level)",
                details={"deep_paths": deep_paths},
                location=str(references_path),
            )

        return self._pass(
            f"References within depth limit ({MAX_REFERENCE_DEPTH} level max)",
            location=str(references_path),
        )
