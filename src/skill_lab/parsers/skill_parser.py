"""Parser for SKILL.md files and skill folder structures."""

import re
from pathlib import Path
from typing import Any

import yaml

from skill_lab.core.models import Skill, SkillMetadata

# Regex pattern for YAML frontmatter
# Allows empty frontmatter (---\n---) as well as content between markers
FRONTMATTER_PATTERN = re.compile(r"^---[ \t]*\r?\n(.*?)^---[ \t]*\r?\n?", re.DOTALL | re.MULTILINE)


def parse_frontmatter(content: str) -> tuple[dict[str, Any] | None, str, list[str]]:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: The full markdown content.

    Returns:
        Tuple of (frontmatter dict or None, body content, list of errors).
    """
    errors: list[str] = []

    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        # No frontmatter found
        return None, content, errors

    frontmatter_text = match.group(1)
    body = content[match.end():]

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if frontmatter is None:
            frontmatter = {}
        if not isinstance(frontmatter, dict):
            errors.append(f"Frontmatter must be a YAML mapping, got {type(frontmatter).__name__}")
            return None, body, errors
    except yaml.YAMLError as e:
        errors.append(f"Failed to parse YAML frontmatter: {e}")
        return None, body, errors

    return frontmatter, body, errors


def extract_metadata(frontmatter: dict[str, Any] | None) -> tuple[SkillMetadata | None, list[str]]:
    """Extract skill metadata from frontmatter.

    Args:
        frontmatter: Parsed frontmatter dictionary.

    Returns:
        Tuple of (SkillMetadata or None, list of errors).
    """
    errors: list[str] = []

    if frontmatter is None:
        return None, errors

    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")

    if not isinstance(name, str):
        name = str(name) if name else ""
        errors.append(f"Name field should be a string, got {type(frontmatter.get('name')).__name__}")

    if not isinstance(description, str):
        description = str(description) if description else ""
        errors.append(
            f"Description field should be a string, got {type(frontmatter.get('description')).__name__}"
        )

    return SkillMetadata(name=name, description=description, raw=frontmatter), errors


def detect_subfolders(skill_path: Path) -> tuple[bool, bool, bool]:
    """Detect presence of standard subfolders in a skill directory.

    Args:
        skill_path: Path to the skill directory.

    Returns:
        Tuple of (has_scripts, has_references, has_assets).
    """
    has_scripts = (skill_path / "scripts").is_dir()
    has_references = (skill_path / "references").is_dir()
    has_assets = (skill_path / "assets").is_dir()
    return has_scripts, has_references, has_assets


def parse_skill(skill_path: Path | str) -> Skill:
    """Parse a skill from its directory.

    Args:
        skill_path: Path to the skill directory.

    Returns:
        Parsed Skill object.
    """
    skill_path = Path(skill_path).resolve()
    errors: list[str] = []

    # Check if path exists and is a directory
    if not skill_path.exists():
        return Skill(
            path=skill_path,
            metadata=None,
            body="",
            has_scripts=False,
            has_references=False,
            has_assets=False,
            parse_errors=(f"Skill path does not exist: {skill_path}",),
        )

    if not skill_path.is_dir():
        return Skill(
            path=skill_path,
            metadata=None,
            body="",
            has_scripts=False,
            has_references=False,
            has_assets=False,
            parse_errors=(f"Skill path is not a directory: {skill_path}",),
        )

    # Look for SKILL.md
    skill_md_path = skill_path / "SKILL.md"
    if not skill_md_path.exists():
        # Also check for lowercase variant
        skill_md_lower = skill_path / "skill.md"
        if skill_md_lower.exists():
            skill_md_path = skill_md_lower
            errors.append("SKILL.md should be uppercase (found skill.md)")
        else:
            return Skill(
                path=skill_path,
                metadata=None,
                body="",
                has_scripts=False,
                has_references=False,
                has_assets=False,
                parse_errors=("SKILL.md file not found",),
            )

    # Read SKILL.md content
    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except OSError as e:
        return Skill(
            path=skill_path,
            metadata=None,
            body="",
            has_scripts=False,
            has_references=False,
            has_assets=False,
            parse_errors=(f"Failed to read SKILL.md: {e}",),
        )

    # Parse frontmatter
    frontmatter, body, fm_errors = parse_frontmatter(content)
    errors.extend(fm_errors)

    # Extract metadata
    metadata, meta_errors = extract_metadata(frontmatter)
    errors.extend(meta_errors)

    # Detect subfolders
    has_scripts, has_references, has_assets = detect_subfolders(skill_path)

    return Skill(
        path=skill_path,
        metadata=metadata,
        body=body,
        has_scripts=has_scripts,
        has_references=has_references,
        has_assets=has_assets,
        parse_errors=tuple(errors),
    )
