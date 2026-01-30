"""Structure checks for skill folder organization."""

from typing import ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import register_check

# Valid file extensions for scripts folder
VALID_SCRIPT_EXTENSIONS = {".py", ".sh", ".js", ".ts", ".bash"}

# Valid file extensions for references folder
VALID_REFERENCE_EXTENSIONS = {".md", ".txt", ".rst"}


@register_check
class SkillMdExistsCheck(StaticCheck):
    """Check that SKILL.md file exists."""

    check_id: ClassVar[str] = "structure.skill-md-exists"
    check_name: ClassVar[str] = "SKILL.md Exists"
    description: ClassVar[str] = "SKILL.md file exists in the skill directory"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    spec_required: ClassVar[bool] = True

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
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    spec_required: ClassVar[bool] = True

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


@register_check
class ScriptsValidCheck(StaticCheck):
    """Check that /scripts contains only valid script files."""

    check_id: ClassVar[str] = "structure.scripts-valid"
    check_name: ClassVar[str] = "Scripts Folder Valid"
    description: ClassVar[str] = "/scripts contains only .py, .sh, .js, .ts, .bash files"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE

    def run(self, skill: Skill) -> CheckResult:
        scripts_path = skill.path / "scripts"

        if not scripts_path.exists():
            return self._pass(
                "No scripts folder present (optional)",
            )

        if not scripts_path.is_dir():
            return self._fail(
                "scripts is not a directory",
                location=str(scripts_path),
            )

        invalid_files: list[str] = []
        for item in scripts_path.iterdir():
            if item.is_file() and item.suffix.lower() not in VALID_SCRIPT_EXTENSIONS:
                invalid_files.append(item.name)

        if invalid_files:
            return self._fail(
                f"Scripts folder contains invalid files: {', '.join(invalid_files)}",
                details={
                    "invalid_files": invalid_files,
                    "valid_extensions": list(VALID_SCRIPT_EXTENSIONS),
                },
                location=str(scripts_path),
            )

        return self._pass(
            "Scripts folder contains only valid script files",
            location=str(scripts_path),
        )


@register_check
class ReferencesValidCheck(StaticCheck):
    """Check that /references contains only valid reference files."""

    check_id: ClassVar[str] = "structure.references-valid"
    check_name: ClassVar[str] = "References Folder Valid"
    description: ClassVar[str] = "/references contains only .md, .txt, .rst files"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE

    def run(self, skill: Skill) -> CheckResult:
        references_path = skill.path / "references"

        if not references_path.exists():
            return self._pass(
                "No references folder present (optional)",
            )

        if not references_path.is_dir():
            return self._fail(
                "references is not a directory",
                location=str(references_path),
            )

        invalid_files: list[str] = []
        for item in references_path.iterdir():
            if item.is_file() and item.suffix.lower() not in VALID_REFERENCE_EXTENSIONS:
                invalid_files.append(item.name)

        if invalid_files:
            return self._fail(
                f"References folder contains invalid files: {', '.join(invalid_files)}",
                details={
                    "invalid_files": invalid_files,
                    "valid_extensions": list(VALID_REFERENCE_EXTENSIONS),
                },
                location=str(references_path),
            )

        return self._pass(
            "References folder contains only valid reference files",
            location=str(references_path),
        )


