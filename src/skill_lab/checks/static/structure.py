"""Structure checks for skill folder organization."""

import re
from typing import ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import register_check

# Valid file extensions for scripts folder
VALID_SCRIPT_EXTENSIONS = {".py", ".sh", ".js", ".ts", ".bash", ".rb"}

# Valid file extensions for references folder
VALID_REFERENCE_EXTENSIONS = {".md", ".txt", ".rst"}


@register_check
class SkillMdExistsCheck(StaticCheck):
    """Check that SKILL.md file exists."""

    check_id: ClassVar[str] = "structure.skill-md-exists"
    check_name: ClassVar[str] = "SKILL.md Exists"
    description: ClassVar[str] = "SKILL.md file exists in the skill directory"
    severity: ClassVar[Severity] = Severity.HIGH
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    spec_required: ClassVar[bool] = True
    fix: ClassVar[str] = "Create a SKILL.md file in this directory"

    def run(self, skill: Skill) -> CheckResult:
        skill_md_path = skill.path / "SKILL.md"

        if skill_md_path.exists():
            return self._pass(
                "SKILL.md found",
                location=str(skill_md_path),
            )

        # Check for lowercase variant
        skill_md_lower = skill.path / "skill.md"
        if skill_md_lower.exists():
            return self._fail(
                "SKILL.md should be uppercase (found skill.md)",
                location=str(skill_md_lower),
            )

        return self._fail(
            "SKILL.md file not found",
            location=str(skill.path),
        )


@register_check
class ValidFrontmatterCheck(StaticCheck):
    """Check that YAML frontmatter is parseable."""

    check_id: ClassVar[str] = "structure.valid-frontmatter"
    check_name: ClassVar[str] = "Valid Frontmatter"
    description: ClassVar[str] = "YAML frontmatter is parseable and valid"
    severity: ClassVar[Severity] = Severity.HIGH
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    spec_required: ClassVar[bool] = True
    fix: ClassVar[str] = "Fix the YAML syntax errors in your SKILL.md frontmatter"

    def run(self, skill: Skill) -> CheckResult:
        # Check for parse errors related to frontmatter
        frontmatter_errors = [e for e in skill.parse_errors if "frontmatter" in e.lower()]

        if frontmatter_errors:
            return self._fail(
                "Invalid YAML frontmatter",
                details={"errors": frontmatter_errors},
                location=self._skill_md_location(skill),
            )

        if skill.metadata is None:
            return self._fail(
                "No frontmatter found in SKILL.md",
                location=self._skill_md_location(skill),
            )

        return self._pass(
            "Valid YAML frontmatter",
            location=self._skill_md_location(skill),
        )


def _validate_folder_extensions(
    check: StaticCheck,
    skill: Skill,
    folder_name: str,
    valid_extensions: set[str],
    file_type: str,
) -> CheckResult:
    """Validate that a folder contains only files with allowed extensions.

    Args:
        check: The check instance (for _pass/_fail helpers).
        skill: The skill being evaluated.
        folder_name: Folder name relative to skill root (e.g., "scripts").
        valid_extensions: Set of allowed file extensions (e.g., {".py", ".sh"}).
        file_type: Human label for messages (e.g., "script", "reference").

    Returns:
        CheckResult indicating pass or fail.
    """
    folder_path = skill.path / folder_name

    if not folder_path.exists():
        return check._pass(f"No {folder_name} folder present (optional)")

    if not folder_path.is_dir():
        return check._fail(
            f"{folder_name} is not a directory",
            location=str(folder_path),
        )

    invalid_files: list[str] = []
    for item in folder_path.iterdir():
        if item.is_file() and item.suffix.lower() not in valid_extensions:
            invalid_files.append(item.name)

    if invalid_files:
        return check._fail(
            f"{folder_name.capitalize()} folder contains invalid files: {', '.join(invalid_files)}",
            details={
                "invalid_files": invalid_files,
                "valid_extensions": list(valid_extensions),
            },
            location=str(folder_path),
        )

    return check._pass(
        f"{folder_name.capitalize()} folder contains only valid {file_type} files",
        location=str(folder_path),
    )


@register_check
class ScriptsValidCheck(StaticCheck):
    """Check that /scripts contains only valid script files."""

    check_id: ClassVar[str] = "structure.scripts-valid"
    check_name: ClassVar[str] = "Scripts Folder Valid"
    description: ClassVar[str] = "/scripts contains only .py, .sh, .js, .ts, .bash, .rb files"
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    fix: ClassVar[str] = (
        "Remove invalid files from scripts/ — only .py .sh .js .ts .bash .rb allowed"
    )

    def run(self, skill: Skill) -> CheckResult:
        return _validate_folder_extensions(
            self, skill, "scripts", VALID_SCRIPT_EXTENSIONS, "script"
        )


@register_check
class ReferencesValidCheck(StaticCheck):
    """Check that /references contains only valid reference files."""

    check_id: ClassVar[str] = "structure.references-valid"
    check_name: ClassVar[str] = "References Folder Valid"
    description: ClassVar[str] = "/references contains only .md, .txt, .rst files"
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    fix: ClassVar[str] = "Remove invalid files from references/ — only .md .txt .rst allowed"

    def run(self, skill: Skill) -> CheckResult:
        return _validate_folder_extensions(
            self, skill, "references", VALID_REFERENCE_EXTENSIONS, "reference"
        )


# Official Agent Skills spec frontmatter fields
# https://agentskills.io/specification
SPEC_FRONTMATTER_FIELDS = {
    "name",  # required
    "description",  # required
    "license",  # optional
    "compatibility",  # optional
    "metadata",  # optional
    "allowed-tools",  # optional/experimental
}


@register_check
class StandardFrontmatterFieldsCheck(StaticCheck):
    """Check that frontmatter only contains spec-defined fields."""

    check_id: ClassVar[str] = "structure.standard-frontmatter-fields"
    check_name: ClassVar[str] = "Standard Frontmatter Fields"
    description: ClassVar[str] = "Frontmatter contains only fields defined in the Agent Skills spec"
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    fix: ClassVar[str] = "Move these non-standard fields into the metadata map"

    def run(self, skill: Skill) -> CheckResult:
        # Check if metadata exists
        if skill.metadata is None:
            return self._pass(
                "No frontmatter to check",
                location=self._skill_md_location(skill),
            )

        # Get all fields from raw frontmatter
        raw_fields = set(skill.metadata.raw.keys())

        # Find non-standard fields
        non_standard = raw_fields - SPEC_FRONTMATTER_FIELDS

        if non_standard:
            sorted_fields = sorted(non_standard)
            return self._fail(
                f"Non-standard frontmatter fields: {', '.join(sorted_fields)}. "
                "Move custom fields to the metadata map",
                details={
                    "non_standard_fields": sorted_fields,
                    "spec_fields": sorted(SPEC_FRONTMATTER_FIELDS),
                    "note": "Custom fields should be placed in the metadata map instead",
                },
                location=self._skill_md_location(skill),
            )

        return self._pass(
            "All frontmatter fields are spec-compliant",
            location=self._skill_md_location(skill),
        )


# Interactive patterns by file extension — language-specific to avoid false positives
_INTERACTIVE_PATTERNS: dict[frozenset[str], list[tuple[str, re.Pattern[str]]]] = {
    # Python: input() and getpass
    frozenset({".py"}): [
        ("input(", re.compile(r"^[^#]*\binput\s*\(")),
        ("getpass.getpass(", re.compile(r"^[^#]*\bgetpass\.getpass\s*\(")),
    ],
    # Shell: read and select builtins
    frozenset({".sh", ".bash"}): [
        ("read", re.compile(r"^[^#]*\bread\b")),
        ("select", re.compile(r"^[^#]*\bselect\b")),
    ],
    # Ruby: gets and STDIN.gets
    frozenset({".rb"}): [
        ("gets", re.compile(r"^[^#]*\bgets\b")),
        ("STDIN.gets", re.compile(r"^[^#]*\bSTDIN\.gets\b")),
    ],
    # JS/TS: readline, prompt(), process.stdin
    frozenset({".js", ".ts"}): [
        ("readline", re.compile(r"^[^/]*\breadline\b")),
        ("prompt(", re.compile(r"^[^/]*\bprompt\s*\(")),
        ("process.stdin", re.compile(r"^[^/]*\bprocess\.stdin\b")),
    ],
}


@register_check
class ScriptsNoInteractiveCheck(StaticCheck):
    """Check that scripts do not use interactive input patterns."""

    check_id: ClassVar[str] = "structure.scripts-no-interactive"
    check_name: ClassVar[str] = "Scripts No Interactive Input"
    description: ClassVar[str] = (
        "Scripts do not use interactive input (agents run non-interactive shells)"
    )
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    fix: ClassVar[str] = "Remove interactive input calls — scripts must run non-interactively"

    def run(self, skill: Skill) -> CheckResult:
        scripts_path = skill.path / "scripts"

        if not scripts_path.exists() or not scripts_path.is_dir():
            return self._pass("No scripts folder present (optional)")

        violations: list[str] = []

        for item in scripts_path.iterdir():
            if not item.is_file():
                continue
            ext = item.suffix.lower()

            # Find which pattern group applies to this extension
            patterns: list[tuple[str, re.Pattern[str]]] = []
            for ext_group, group_patterns in _INTERACTIVE_PATTERNS.items():
                if ext in ext_group:
                    patterns = group_patterns
                    break

            if not patterns:
                continue

            try:
                content = item.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for line in content.splitlines():
                for label, pattern in patterns:
                    if pattern.search(line):
                        violations.append(f"{item.name}: {label}")

        if violations:
            return self._fail(
                f"Scripts contain interactive input patterns: {', '.join(violations)}",
                details={"violations": violations},
                location=str(scripts_path),
            )

        return self._pass(
            "Scripts do not use interactive input",
            location=str(scripts_path),
        )


# Dependency manifests that indicate non-self-contained scripts
_DEPENDENCY_MANIFESTS: dict[str, str] = {
    "requirements.txt": "Use inline script metadata (PEP 723) or pip install in the script",
    "package.json": "Use npx or bundle dependencies inline",
    "Gemfile": "Use inline gem install or bundler inline",
    "go.mod": "Use go run with module-aware mode",
    "deno.json": "Use URL imports instead of a config file",
}


@register_check
class ScriptsSelfContainedCheck(StaticCheck):
    """Check that scripts/ has no loose dependency manifests."""

    check_id: ClassVar[str] = "structure.scripts-self-contained"
    check_name: ClassVar[str] = "Scripts Self-Contained"
    description: ClassVar[str] = "Scripts folder has no loose dependency manifests"
    severity: ClassVar[Severity] = Severity.LOW
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    fix: ClassVar[str] = "Remove dependency manifests from scripts/ and embed dependencies inline"

    def run(self, skill: Skill) -> CheckResult:
        scripts_path = skill.path / "scripts"

        if not scripts_path.exists() or not scripts_path.is_dir():
            return self._pass("No scripts folder present (optional)")

        found: dict[str, str] = {}
        for manifest, suggestion in _DEPENDENCY_MANIFESTS.items():
            if (scripts_path / manifest).exists():
                found[manifest] = suggestion

        if found:
            names = ", ".join(sorted(found))
            return self._fail(
                f"Scripts folder contains dependency manifests: {names}",
                details={
                    "manifests": list(found.keys()),
                    "suggestions": found,
                },
                location=str(scripts_path),
            )

        return self._pass(
            "Scripts folder is self-contained (no dependency manifests)",
            location=str(scripts_path),
        )
