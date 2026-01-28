"""Tests for static checks."""

from pathlib import Path

import pytest

from skill_lab.checks.static.content import (
    BodyNotEmptyCheck,
    HasExamplesCheck,
    LineBudgetCheck,
    NoTimeSensitiveCheck,
    NoWindowsPathsCheck,
)
from skill_lab.checks.static.description import (
    DescriptionMaxLengthCheck,
    DescriptionNotEmptyCheck,
    DescriptionRequiredCheck,
    DescriptionThirdPersonCheck,
)
from skill_lab.checks.static.naming import (
    GerundConventionCheck,
    NameFormatCheck,
    NameMatchesDirectoryCheck,
    NameRequiredCheck,
    NoReservedWordsCheck,
)
from skill_lab.checks.static.structure import (
    NoUnexpectedFilesCheck,
    SkillMdExistsCheck,
    ValidFrontmatterCheck,
)
from skill_lab.core.models import Severity, Skill, SkillMetadata


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


class TestNamingChecks:
    """Tests for naming checks."""

    def test_name_required_pass(self):
        check = NameRequiredCheck()
        skill = make_skill(name="my-skill")
        result = check.run(skill)
        assert result.passed

    def test_name_required_fail(self):
        check = NameRequiredCheck()
        skill = make_skill(name="")
        result = check.run(skill)
        assert not result.passed

    def test_name_format_valid(self):
        check = NameFormatCheck()
        for valid_name in ["my-skill", "skill123", "a", "creating-reports"]:
            skill = make_skill(name=valid_name)
            result = check.run(skill)
            assert result.passed, f"Expected '{valid_name}' to pass"

    def test_name_format_invalid(self):
        check = NameFormatCheck()
        for invalid_name in ["My_Skill", "UPPERCASE", "spaces here", "-starts-with-hyphen"]:
            skill = make_skill(name=invalid_name)
            result = check.run(skill)
            assert not result.passed, f"Expected '{invalid_name}' to fail"

    def test_no_reserved_words_pass(self):
        check = NoReservedWordsCheck()
        skill = make_skill(name="my-awesome-skill")
        result = check.run(skill)
        assert result.passed

    def test_no_reserved_words_fail(self):
        check = NoReservedWordsCheck()
        for reserved in ["claude-helper", "anthropic-tool", "my-gpt-skill"]:
            skill = make_skill(name=reserved)
            result = check.run(skill)
            assert not result.passed, f"Expected '{reserved}' to fail"
            assert result.severity == Severity.WARNING  # Quality suggestion, not in spec

    def test_gerund_convention_pass(self):
        check = GerundConventionCheck()
        for gerund_name in ["creating-reports", "managing-files", "building-apps"]:
            skill = make_skill(name=gerund_name)
            result = check.run(skill)
            assert result.passed, f"Expected '{gerund_name}' to pass"

    def test_gerund_convention_fail(self):
        check = GerundConventionCheck()
        skill = make_skill(name="report-maker")
        result = check.run(skill)
        assert not result.passed
        assert result.severity == Severity.INFO  # Quality suggestion, not in spec

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
        check = DescriptionRequiredCheck()
        skill = make_skill(description="Some description")
        result = check.run(skill)
        assert result.passed

    def test_description_not_empty_pass(self):
        check = DescriptionNotEmptyCheck()
        skill = make_skill(description="Valid description")
        result = check.run(skill)
        assert result.passed

    def test_description_not_empty_fail(self):
        check = DescriptionNotEmptyCheck()
        skill = make_skill(description="   ")
        result = check.run(skill)
        assert not result.passed

    def test_description_max_length_pass(self):
        check = DescriptionMaxLengthCheck()
        skill = make_skill(description="Short description")
        result = check.run(skill)
        assert result.passed

    def test_description_max_length_fail(self):
        check = DescriptionMaxLengthCheck()
        skill = make_skill(description="x" * 2000)
        result = check.run(skill)
        assert not result.passed

    def test_description_third_person_pass(self):
        check = DescriptionThirdPersonCheck()
        skill = make_skill(description="Creates reports for users when requested.")
        result = check.run(skill)
        assert result.passed

    def test_description_third_person_fail(self):
        check = DescriptionThirdPersonCheck()
        skill = make_skill(description="I will help you create reports.")
        result = check.run(skill)
        assert not result.passed
        assert result.severity == Severity.INFO  # Quality suggestion, not in spec


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

    def test_no_windows_paths_pass(self):
        check = NoWindowsPathsCheck()
        skill = make_skill(body="Use path /usr/local/bin")
        result = check.run(skill)
        assert result.passed

    def test_no_windows_paths_fail(self):
        check = NoWindowsPathsCheck()
        skill = make_skill(body="Use path C:\\Users\\test")
        result = check.run(skill)
        assert not result.passed
        assert result.severity == Severity.INFO  # Quality suggestion, not in spec

    def test_no_time_sensitive_pass(self):
        check = NoTimeSensitiveCheck()
        skill = make_skill(body="This works with version 1.0.0")
        result = check.run(skill)
        assert result.passed

    def test_no_time_sensitive_fail(self):
        check = NoTimeSensitiveCheck()
        skill = make_skill(body="Updated on 2024-01-15")
        result = check.run(skill)
        assert not result.passed
        assert result.severity == Severity.INFO  # Quality suggestion, not in spec
