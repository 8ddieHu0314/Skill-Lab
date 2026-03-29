"""Content checks for SKILL.md body and quality."""

import re
from pathlib import Path, PurePosixPath
from typing import ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.checks.static.structure import VALID_SCRIPT_EXTENSIONS
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import register_check
from skill_lab.core.tokens import estimate_tokens

# Maximum line count for skill body
MAX_LINE_COUNT = 500

# Maximum token count for skill body (spec recommends ≤5,000)
MAX_BODY_TOKENS = 5000

# Maximum token count for metadata (name + description) for context-efficient discovery
MAX_METADATA_TOKENS = 150

# Activation phrases that help agents match tasks to this skill
_ACTIVATION_PHRASES = (
    "use when",
    "use for",
    "use this",
    "trigger",
    "activate",
    "invoke",
    "run when",
    "run this",
    "helps with",
    "designed for",
    "intended for",
    "works with",
)

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
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Add instructions and context to your SKILL.md body"

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
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Trim your SKILL.md body to under 500 lines"

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
    severity: ClassVar[Severity] = Severity.LOW
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Add code examples using fenced code blocks"

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
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Flatten your references/ folder — keep it to 1 level deep"

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
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Mention your script filenames in the SKILL.md body"

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


def _check_paths_exist(
    check: StaticCheck,
    skill: Skill,
    pattern: re.Pattern[str],
    label: str,
) -> CheckResult:
    """Check that paths matching a regex in the body exist on disk.

    Args:
        check: The check instance (for _pass/_fail helpers).
        skill: The skill being evaluated.
        pattern: Regex pattern to find path references in the body.
        label: Human label for messages (e.g., "script", "asset").

    Returns:
        CheckResult indicating pass or fail.
    """
    refs = pattern.findall(skill.body)

    if not refs:
        return check._pass(
            f"No {label} path references in body",
            location=check._skill_md_location(skill),
        )

    unique_refs = list(dict.fromkeys(refs))
    missing = [ref for ref in unique_refs if not (skill.path / ref).exists()]

    if missing:
        return check._fail(
            f"{label.capitalize()} path(s) not found on disk: {', '.join(missing)}",
            details={"missing_paths": missing, "all_references": unique_refs},
            location=check._skill_md_location(skill),
        )

    return check._pass(
        f"All referenced {label} paths exist ({len(unique_refs)} verified)",
        location=check._skill_md_location(skill),
    )


@register_check
class ScriptPathsExistCheck(StaticCheck):
    """Check that script paths referenced in body exist on disk."""

    check_id: ClassVar[str] = "content.script-paths-exist"
    check_name: ClassVar[str] = "Script Paths Exist"
    description: ClassVar[str] = "Script paths referenced in body resolve to files on disk"
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Create the missing script files or fix the paths in your SKILL.md body"

    def run(self, skill: Skill) -> CheckResult:
        return _check_paths_exist(self, skill, _SCRIPT_PATH_RE, "script")


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
    severity: ClassVar[Severity] = Severity.LOW
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Add required runtimes to the compatibility: field"

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


@register_check
class TokenBudgetCheck(StaticCheck):
    """Check that body instructions stay under the spec-recommended 5,000 token budget."""

    check_id: ClassVar[str] = "content.token-budget"
    check_name: ClassVar[str] = "Token Budget"
    description: ClassVar[str] = f"Body is under {MAX_BODY_TOKENS} tokens"
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Trim your SKILL.md body to under 5000 tokens"

    def run(self, skill: Skill) -> CheckResult:
        tokens = estimate_tokens(skill.body)

        if tokens > MAX_BODY_TOKENS:
            return self._fail(
                f"Body exceeds {MAX_BODY_TOKENS} token budget ({tokens} estimated)",
                details={"estimated_tokens": tokens, "max_tokens": MAX_BODY_TOKENS},
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"Body within token budget ({tokens}/{MAX_BODY_TOKENS})",
            location=self._skill_md_location(skill),
        )


@register_check
class MetadataTokenBudgetCheck(StaticCheck):
    """Check that metadata (name + description) fits the ~100-token discovery budget."""

    check_id: ClassVar[str] = "content.metadata-token-budget"
    check_name: ClassVar[str] = "Metadata Token Budget"
    description: ClassVar[str] = (
        f"Metadata is under {MAX_METADATA_TOKENS} tokens for efficient discovery"
    )
    severity: ClassVar[Severity] = Severity.LOW
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Shorten your name or description to under 150 tokens"

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None:
            return self._pass(
                "No metadata to check",
                location=self._skill_md_location(skill),
            )

        combined = f"{skill.metadata.name} {skill.metadata.description}"
        tokens = estimate_tokens(combined)

        if tokens > MAX_METADATA_TOKENS:
            return self._fail(
                f"Metadata exceeds {MAX_METADATA_TOKENS} token budget ({tokens} estimated)",
                details={"estimated_tokens": tokens, "max_tokens": MAX_METADATA_TOKENS},
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"Metadata within token budget ({tokens}/{MAX_METADATA_TOKENS})",
            location=self._skill_md_location(skill),
        )


@register_check
class DescriptionActionableCheck(StaticCheck):
    """Check that description includes activation phrasing for agent matching."""

    check_id: ClassVar[str] = "content.description-actionable"
    check_name: ClassVar[str] = "Description Actionable"
    description: ClassVar[str] = "Description explains when to use this skill"
    severity: ClassVar[Severity] = Severity.LOW
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Add 'Use when...' phrasing to describe when to trigger this skill"

    def run(self, skill: Skill) -> CheckResult:
        if skill.metadata is None or not skill.metadata.description.strip():
            return self._pass(
                "No description to check (other checks catch this)",
                location=self._skill_md_location(skill),
            )

        desc_lower = skill.metadata.description.lower()
        for phrase in _ACTIVATION_PHRASES:
            if phrase in desc_lower:
                return self._pass(
                    f"Description contains activation phrase: '{phrase}'",
                    location=self._skill_md_location(skill),
                )

        return self._fail(
            "Description lacks activation phrasing for agent matching",
            details={
                "suggestion": "Add 'Use when...' or 'Designed for...' phrasing "
                "to help agents match tasks to this skill",
            },
            location=self._skill_md_location(skill),
        )


# Regex to match assets/<file>.<ext> references in body
_ASSET_PATH_RE = re.compile(r"(?<![/\w-])assets/[\w.-]+\.\w+\b")


@register_check
class AssetPathsExistCheck(StaticCheck):
    """Check that asset paths referenced in body exist on disk."""

    check_id: ClassVar[str] = "content.asset-paths-exist"
    check_name: ClassVar[str] = "Asset Paths Exist"
    description: ClassVar[str] = "Asset paths referenced in body resolve to files on disk"
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Create the missing asset files or fix the paths in your SKILL.md body"

    def run(self, skill: Skill) -> CheckResult:
        return _check_paths_exist(self, skill, _ASSET_PATH_RE, "asset")


# Regex to match markdown links [text](path) — excludes URLs, anchors, and mailto
_INTERNAL_LINK_RE = re.compile(r"\[(?:[^\]]*)\]\((?!(?:https?|ftp|mailto)://|#)((?:\./)?\S+?)\)")

# Spec directories that contain skill support files
_SPEC_DIRS = ("references", "assets", "scripts")


@register_check
class BrokenInternalLinksCheck(StaticCheck):
    """Check that markdown links to local files resolve on disk."""

    check_id: ClassVar[str] = "content.broken-internal-links"
    check_name: ClassVar[str] = "Broken Internal Links"
    description: ClassVar[str] = "Markdown links to local files resolve on disk"
    severity: ClassVar[Severity] = Severity.MEDIUM
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Fix broken file paths in your markdown links or create the missing files"

    def run(self, skill: Skill) -> CheckResult:
        refs = _INTERNAL_LINK_RE.findall(skill.body)

        if not refs:
            return self._pass(
                "No internal file links in body",
                location=self._skill_md_location(skill),
            )

        unique_refs: list[str] = list(dict.fromkeys(refs))
        missing: list[str] = []

        for ref in unique_refs:
            # Strip any trailing parentheses or punctuation that leaked into the match
            clean = ref.rstrip(")")
            target = skill.path / PurePosixPath(clean)
            if not target.exists():
                missing.append(clean)

        if missing:
            return self._fail(
                f"Broken internal link(s): {', '.join(missing)}",
                details={"missing_paths": missing, "all_links": unique_refs},
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"All internal links resolve ({len(unique_refs)} verified)",
            location=self._skill_md_location(skill),
        )


@register_check
class OrphanedFilesCheck(StaticCheck):
    """Check that files in spec directories are referenced from SKILL.md."""

    check_id: ClassVar[str] = "content.orphaned-files"
    check_name: ClassVar[str] = "Orphaned Files"
    description: ClassVar[str] = "Files in spec directories are referenced from SKILL.md"
    severity: ClassVar[Severity] = Severity.LOW
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    fix: ClassVar[str] = "Reference orphaned files in your SKILL.md body or remove them"

    def run(self, skill: Skill) -> CheckResult:
        # Collect all files in spec directories
        all_files: list[Path] = []
        for spec_dir in _SPEC_DIRS:
            dir_path = skill.path / spec_dir
            if dir_path.is_dir():
                all_files.extend(f for f in dir_path.rglob("*") if f.is_file())

        if not all_files:
            return self._pass(
                "No files in spec directories to check",
            )

        body = skill.body

        # First pass: find files directly referenced in body
        referenced: set[str] = set()
        for f in all_files:
            rel = str(f.relative_to(skill.path))
            # Check both full relative path and just the filename
            if rel in body or f.name in body:
                referenced.add(rel)

        # Second pass: read directly-referenced .md files and extract their links
        for ref_str in list(referenced):
            ref_path = skill.path / ref_str
            if ref_path.suffix.lower() == ".md":
                try:
                    ref_content = ref_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                # Find links in the referenced file
                for link in _INTERNAL_LINK_RE.findall(ref_content):
                    clean = link.rstrip(")")
                    # Resolve relative to the referenced file's parent
                    linked_path = (ref_path.parent / PurePosixPath(clean)).resolve()
                    try:
                        linked_rel = str(linked_path.relative_to(skill.path))
                        referenced.add(linked_rel)
                    except ValueError:
                        pass

        # Find orphans
        orphans: list[str] = []
        for f in all_files:
            rel = str(f.relative_to(skill.path))
            if rel not in referenced:
                orphans.append(rel)

        if orphans:
            return self._fail(
                f"{len(orphans)} orphaned file(s) in spec directories: "
                f"{', '.join(sorted(orphans)[:5])}"
                + (f" (and {len(orphans) - 5} more)" if len(orphans) > 5 else ""),
                details={"orphaned_files": sorted(orphans), "total": len(orphans)},
            )

        return self._pass(
            f"All {len(all_files)} file(s) in spec directories are referenced",
        )
