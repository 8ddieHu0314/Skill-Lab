"""Tests for static checks."""

from pathlib import Path

import pytest

from skill_lab.checks.static.content import (
    BodyNotEmptyCheck,
    HasExamplesCheck,
    LineBudgetCheck,
)
from skill_lab.checks.static.description import (
    DescriptionIncludesTriggersCheck,
)
from skill_lab.checks.static.naming import (
    NameMatchesDirectoryCheck,
)
from skill_lab.checks.static.structure import (
    SkillMdExistsCheck,
    StandardFrontmatterFieldsCheck,
    ValidFrontmatterCheck,
)
from skill_lab.core.models import Severity, Skill, SkillMetadata
from skill_lab.core.registry import registry

# Ensure schema checks are registered
from skill_lab.checks.static import schema as _schema  # noqa: F401


def _get_check(check_id: str):
    """Get a check instance from the registry by ID."""
    check_class = registry.get(check_id)
    assert check_class is not None, f"Check '{check_id}' not found in registry"
    return check_class()


def make_skill(
    name: str = "test-skill",
    description: str = "A test skill description",
    body: str = "This is the skill body content with enough text.",
    parse_errors: tuple = (),
    path: Path | None = None,
) -> Skill:
    """Helper to create a Skill for testing."""
    return Skill(
        path=path or Path("/test/skill"),
        metadata=SkillMetadata(name=name, description=description, raw={"name": name, "description": description}),
        body=body,
        has_scripts=False,
        has_references=False,
        has_assets=False,
        parse_errors=parse_errors,
    )


class TestStructureChecks:
    """Tests for structure checks."""

    def test_skill_md_exists_pass(self, valid_skill_path: Path):
        check = SkillMdExistsCheck()
        skill = Skill(
            path=valid_skill_path,
            metadata=None,
            body="",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed

    def test_valid_frontmatter_pass(self):
        check = ValidFrontmatterCheck()
        skill = make_skill()
        result = check.run(skill)
        assert result.passed

    def test_valid_frontmatter_fail_no_metadata(self):
        check = ValidFrontmatterCheck()
        skill = Skill(
            path=Path("/test"),
            metadata=None,
            body="Body",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed

    def test_standard_frontmatter_fields_pass(self):
        """Test that standard spec fields pass."""
        check = StandardFrontmatterFieldsCheck()
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "license": "MIT",
                    "compatibility": "Requires Python 3.10+",
                    "metadata": {"author": "test"},
                    "allowed-tools": "Read Write Bash",
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed
        assert result.severity == Severity.WARNING

    def test_standard_frontmatter_fields_fail_non_standard(self):
        """Test that non-standard fields trigger a warning."""
        check = StandardFrontmatterFieldsCheck()
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "argument-hint": "[topic]",  # non-standard
                    "disable-model-invocation": True,  # non-standard
                    "context": "fork",  # non-standard
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert result.severity == Severity.WARNING
        assert "argument-hint" in result.message
        assert "context" in result.message
        assert "disable-model-invocation" in result.message

    def test_standard_frontmatter_fields_no_metadata(self):
        """Test that missing metadata passes (nothing to check)."""
        check = StandardFrontmatterFieldsCheck()
        skill = Skill(
            path=Path("/test"),
            metadata=None,
            body="Body",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed


class TestNamingChecks:
    """Tests for naming checks."""

    def test_name_required_pass(self):
        check = _get_check("naming.required")
        skill = make_skill(name="my-skill")
        result = check.run(skill)
        assert result.passed

    def test_name_required_fail(self):
        check = _get_check("naming.required")
        skill = make_skill(name="")
        result = check.run(skill)
        assert not result.passed

    def test_name_format_valid(self):
        check = _get_check("naming.format")
        # Per spec: lowercase alphanumeric + hyphens, no start/end hyphen
        for valid_name in ["my-skill", "skill123", "a", "creating-reports", "30daysresearch", "123", "1"]:
            skill = make_skill(name=valid_name)
            result = check.run(skill)
            assert result.passed, f"Expected '{valid_name}' to pass"

    def test_name_format_invalid(self):
        check = _get_check("naming.format")
        # Invalid: uppercase, underscores, spaces, start/end with hyphen, consecutive hyphens
        for invalid_name in ["My_Skill", "UPPERCASE", "spaces here", "-starts-with-hyphen", "ends-with-hyphen-", "has--consecutive-hyphens"]:
            skill = make_skill(name=invalid_name)
            result = check.run(skill)
            assert not result.passed, f"Expected '{invalid_name}' to fail"

    def test_name_matches_directory_pass(self):
        check = NameMatchesDirectoryCheck()
        skill = make_skill(name="my-skill", path=Path("/test/my-skill"))
        result = check.run(skill)
        assert result.passed

    def test_name_matches_directory_fail(self):
        check = NameMatchesDirectoryCheck()
        skill = make_skill(name="different-name", path=Path("/test/my-skill"))
        result = check.run(skill)
        assert not result.passed
        assert result.severity == Severity.ERROR


class TestDescriptionChecks:
    """Tests for description checks."""

    def test_description_required_pass(self):
        check = _get_check("description.required")
        skill = make_skill(description="Some description")
        result = check.run(skill)
        assert result.passed

    def test_description_not_empty_pass(self):
        check = _get_check("description.not-empty")
        skill = make_skill(description="Valid description")
        result = check.run(skill)
        assert result.passed

    def test_description_not_empty_fail(self):
        check = _get_check("description.not-empty")
        skill = make_skill(description="   ")
        result = check.run(skill)
        assert not result.passed

    def test_description_max_length_pass(self):
        check = _get_check("description.max-length")
        skill = make_skill(description="Short description")
        result = check.run(skill)
        assert result.passed

    def test_description_max_length_fail(self):
        check = _get_check("description.max-length")
        skill = make_skill(description="x" * 2000)
        result = check.run(skill)
        assert not result.passed



class TestContentChecks:
    """Tests for content checks."""

    def test_body_not_empty_pass(self):
        check = BodyNotEmptyCheck()
        skill = make_skill(body="This is some meaningful content that is long enough to pass the minimum requirement.")
        result = check.run(skill)
        assert result.passed

    def test_body_not_empty_fail(self):
        check = BodyNotEmptyCheck()
        skill = make_skill(body="")
        result = check.run(skill)
        assert not result.passed
        assert result.severity == Severity.WARNING  # Quality suggestion, spec allows empty body

    def test_body_too_short(self):
        check = BodyNotEmptyCheck()
        skill = make_skill(body="Short")
        result = check.run(skill)
        assert not result.passed

    def test_line_budget_pass(self):
        check = LineBudgetCheck()
        skill = make_skill(body="Line 1\nLine 2\nLine 3")
        result = check.run(skill)
        assert result.passed

    def test_line_budget_fail(self):
        check = LineBudgetCheck()
        skill = make_skill(body="\n".join(["Line"] * 600))
        result = check.run(skill)
        assert not result.passed

    def test_has_examples_pass(self):
        check = HasExamplesCheck()
        skill = make_skill(body="# Title\n\n```python\ncode here\n```")
        result = check.run(skill)
        assert result.passed

    def test_has_examples_fail(self):
        check = HasExamplesCheck()
        skill = make_skill(body="Just text without any code examples.")
        result = check.run(skill)
        assert not result.passed


class TestFrontmatterChecks:
    """Tests for optional frontmatter field checks."""

    def test_compatibility_valid(self):
        check = _get_check("frontmatter.compatibility-length")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "compatibility": "Requires Python 3.10+",
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed

    def test_compatibility_too_long(self):
        check = _get_check("frontmatter.compatibility-length")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "compatibility": "x" * 501,  # Over 500 chars
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert "exceeds" in result.message

    def test_compatibility_empty_fails(self):
        """Spec requires 1-500 characters if provided."""
        check = _get_check("frontmatter.compatibility-length")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "compatibility": "",  # Empty string
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert "empty" in result.message.lower()

    def test_compatibility_whitespace_only_fails(self):
        """Whitespace-only compatibility should fail."""
        check = _get_check("frontmatter.compatibility-length")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "compatibility": "   ",  # Whitespace only
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed

    def test_metadata_valid(self):
        check = _get_check("frontmatter.metadata-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "metadata": {"author": "test-org", "version": "1.0"},
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed

    def test_metadata_non_string_value_fails(self):
        check = _get_check("frontmatter.metadata-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "metadata": {"author": "test-org", "version": 1.0},  # Number instead of string
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert "string" in result.message.lower()

    def test_allowed_tools_valid(self):
        check = _get_check("frontmatter.allowed-tools-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "allowed-tools": "Read Write Bash",
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed

    def test_allowed_tools_list_fails(self):
        """Using YAML list syntax instead of space-delimited string should fail."""
        check = _get_check("frontmatter.allowed-tools-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "allowed-tools": ["Read", "Write", "Bash"],  # List instead of string
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert "space-delimited" in result.message.lower()

    def test_license_valid_string(self):
        check = _get_check("frontmatter.license-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "license": "Apache-2.0",
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed

    def test_license_absent_passes(self):
        check = _get_check("frontmatter.license-format")
        skill = make_skill()
        result = check.run(skill)
        assert result.passed

    def test_license_non_string_fails(self):
        """YAML can parse 'license: true' as boolean."""
        check = _get_check("frontmatter.license-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "license": True,  # Boolean instead of string
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert "string" in result.message.lower()
