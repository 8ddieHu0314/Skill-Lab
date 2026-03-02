"""Content checks for SKILL.md body and quality."""

import re
from pathlib import Path
from typing import ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.checks.static.structure import VALID_SCRIPT_EXTENSIONS
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


@register_check
class ScriptsReferencedCheck(StaticCheck):
    """Check that scripts in scripts/ are mentioned in SKILL.md body."""

    check_id: ClassVar[str] = "content.scripts-referenced"
    check_name: ClassVar[str] = "Scripts Referenced"
    description: ClassVar[str] = "Scripts in scripts/ are mentioned in the SKILL.md body"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        scripts_path = skill.path / "scripts"

        if not scripts_path.exists() or not scripts_path.is_dir():
            return self._pass("No scripts folder present (optional)")

        script_files = [
            item.name
            for item in scripts_path.iterdir()
            if item.is_file() and item.suffix.lower() in VALID_SCRIPT_EXTENSIONS
        ]

        if not script_files:
            return self._pass(
                "No script files in scripts/",
                location=str(scripts_path),
            )

        body = skill.body
        mentioned = [f for f in script_files if f in body]

        if mentioned:
            return self._pass(
                f"Script(s) mentioned in body: {', '.join(mentioned)}",
                location=self._skill_md_location(skill),
            )

        return self._fail(
            f"Scripts exist but none mentioned in body: {', '.join(sorted(script_files))}",
            details={
                "script_files": sorted(script_files),
                "suggestion": "List available scripts in your SKILL.md so the agent knows they exist",
            },
            location=self._skill_md_location(skill),
        )


# Regex to match scripts/<name>.<ext> references in body
_SCRIPT_EXT_PATTERN = "|".join(ext.lstrip(".") for ext in sorted(VALID_SCRIPT_EXTENSIONS))
_SCRIPT_PATH_RE = re.compile(rf"(?<![/\w-])scripts/[\w.-]+\.(?:{_SCRIPT_EXT_PATTERN})\b")


@register_check
class ScriptPathsExistCheck(StaticCheck):
    """Check that script paths referenced in body exist on disk."""

    check_id: ClassVar[str] = "content.script-paths-exist"
    check_name: ClassVar[str] = "Script Paths Exist"
    description: ClassVar[str] = "Script paths referenced in body resolve to files on disk"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        refs = _SCRIPT_PATH_RE.findall(skill.body)

        if not refs:
            return self._pass(
                "No script path references in body",
                location=self._skill_md_location(skill),
            )

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_refs: list[str] = []
        for ref in refs:
            if ref not in seen:
                seen.add(ref)
                unique_refs.append(ref)

        missing = [ref for ref in unique_refs if not (skill.path / ref).exists()]

        if missing:
            return self._fail(
                f"Script path(s) not found on disk: {', '.join(missing)}",
                details={"missing_paths": missing, "all_references": unique_refs},
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"All referenced script paths exist ({len(unique_refs)} verified)",
            location=self._skill_md_location(skill),
        )


# Command runners and their expected runtime mentions in compatibility
_RUNNER_TO_RUNTIME: dict[str, str] = {
    "npx": "Node.js",
    "uvx": "uv",
    "bunx": "Bun",
    "deno run": "Deno",
    "go run": "Go",
    "pipx run": "pipx",
}

# Build a regex that matches any runner keyword (case-insensitive, word boundary)
_RUNNER_RE = re.compile(
    r"\b(" + "|".join(re.escape(r) for r in _RUNNER_TO_RUNTIME) + r")\b",
    re.IGNORECASE,
)


@register_check
class CompatibilityPrereqsCheck(StaticCheck):
    """Check that command runners in body have matching compatibility entries."""

    check_id: ClassVar[str] = "content.compatibility-prereqs"
    check_name: ClassVar[str] = "Compatibility Prerequisites"
    description: ClassVar[str] = "Command runners in body are documented in compatibility field"
    severity: ClassVar[Severity] = Severity.INFO
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        matches = _RUNNER_RE.findall(skill.body)

        if not matches:
            return self._pass(
                "No command runners referenced in body",
                location=self._skill_md_location(skill),
            )

        # Normalize matches to canonical form (lowercase lookup)
        runners_found: dict[str, str] = {}
        for match in matches:
            canonical = match.lower()
            if canonical not in runners_found:
                runners_found[canonical] = _RUNNER_TO_RUNTIME.get(
                    canonical, _RUNNER_TO_RUNTIME.get(match, match)
                )

        # Get compatibility field
        compat = ""
        if skill.metadata and skill.metadata.raw.get("compatibility"):
            compat_val = skill.metadata.raw["compatibility"]
            if isinstance(compat_val, str):
                compat = compat_val.lower()

        missing: dict[str, str] = {}
        for runner, runtime in runners_found.items():
            if runtime.lower() not in compat:
                missing[runner] = runtime

        if missing:
            pairs = [f"{r} (needs {rt})" for r, rt in missing.items()]
            return self._fail(
                f"Command runners missing from compatibility: {', '.join(pairs)}",
                details={
                    "missing_runners": missing,
                    "suggestion": "Add runtime prerequisites to the compatibility frontmatter field",
                },
                location=self._skill_md_location(skill),
            )

        return self._pass(
            "All command runners documented in compatibility field",
            location=self._skill_md_location(skill),
        )
