"""Content checks for SKILL.md body and quality."""

import re
from pathlib import Path
from typing import ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import register_check

# Maximum line count for skill body
MAX_LINE_COUNT = 500

# Pattern for Windows-style paths
WINDOWS_PATH_PATTERN = re.compile(r"[A-Za-z]:\\|\\\\")

# Pattern for hardcoded dates (common formats)
DATE_PATTERNS = [
    r"\b\d{4}-\d{2}-\d{2}\b",  # 2024-01-15
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",  # 1/15/2024 or 01/15/24
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",  # January 15, 2024
]

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
    """Check that SKILL.md body has content."""

    check_id: ClassVar[str] = "content.body-not-empty"
    check_name: ClassVar[str] = "Body Not Empty"
    description: ClassVar[str] = "SKILL.md body has meaningful content"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        body = skill.body.strip()

        if not body:
            return self._fail(
                "SKILL.md body is empty",
                location=str(skill.path / "SKILL.md"),
            )

        # Check for minimal content (at least 50 characters of actual content)
        if len(body) < 50:
            return self._fail(
                f"SKILL.md body is too short ({len(body)} characters)",
                details={"length": len(body), "minimum": 50},
                location=str(skill.path / "SKILL.md"),
            )

        return self._pass(
            f"SKILL.md body has content ({len(body)} characters)",
            location=str(skill.path / "SKILL.md"),
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
                location=str(skill.path / "SKILL.md"),
            )

        return self._pass(
            f"Body within line budget ({line_count}/{MAX_LINE_COUNT})",
            location=str(skill.path / "SKILL.md"),
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
                    location=str(skill.path / "SKILL.md"),
                )

        return self._fail(
            "Content does not contain code examples",
            details={"suggestion": "Add code examples using fenced code blocks (```)"},
            location=str(skill.path / "SKILL.md"),
        )


@register_check
class NoWindowsPathsCheck(StaticCheck):
    """Check for Windows-style paths."""

    check_id: ClassVar[str] = "content.no-windows-paths"
    check_name: ClassVar[str] = "No Windows Paths"
    description: ClassVar[str] = "Content does not contain Windows-style paths"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        body = skill.body
        matches = WINDOWS_PATH_PATTERN.findall(body)

        if matches:
            return self._fail(
                f"Content contains Windows-style paths",
                details={
                    "found": matches[:5],
                    "suggestion": "Use forward slashes (/) for cross-platform compatibility",
                },
                location=str(skill.path / "SKILL.md"),
            )

        return self._pass(
            "No Windows-style paths found",
            location=str(skill.path / "SKILL.md"),
        )


@register_check
class NoTimeSensitiveCheck(StaticCheck):
    """Check for hardcoded dates."""

    check_id: ClassVar[str] = "content.no-time-sensitive"
    check_name: ClassVar[str] = "No Time-Sensitive Content"
    description: ClassVar[str] = "Content does not contain hardcoded dates"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        body = skill.body
        found_dates: list[str] = []

        for pattern in DATE_PATTERNS:
            matches = re.findall(pattern, body)
            found_dates.extend(matches)

        if found_dates:
            # Filter out common false positives (version numbers like 1.0.0)
            real_dates = [d for d in found_dates if not re.match(r"^\d+\.\d+\.\d+$", d)]

            if real_dates:
                return self._fail(
                    "Content contains hardcoded dates",
                    details={
                        "found": real_dates[:5],
                        "suggestion": "Avoid hardcoded dates that may become stale",
                    },
                    location=str(skill.path / "SKILL.md"),
                )

        return self._pass(
            "No hardcoded dates found",
            location=str(skill.path / "SKILL.md"),
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
