"""Tests for skill parser."""

from pathlib import Path

from skill_lab.parsers.skill_parser import (
    extract_metadata,
    parse_frontmatter,
    parse_skill,
)


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""

    def test_valid_frontmatter(self):
        content = """---
name: test-skill
description: A test skill
---

Body content here.
"""
        frontmatter, body, errors = parse_frontmatter(content)

        assert frontmatter is not None
        assert frontmatter["name"] == "test-skill"
        assert frontmatter["description"] == "A test skill"
        assert "Body content here." in body
        assert len(errors) == 0

    def test_no_frontmatter(self):
        content = "Just body content without frontmatter."
        frontmatter, body, errors = parse_frontmatter(content)

        assert frontmatter is None
        assert body == content
        assert len(errors) == 0

    def test_invalid_yaml(self):
        content = """---
name: test
invalid: [unclosed bracket
---

Body content.
"""
        frontmatter, body, errors = parse_frontmatter(content)

        assert frontmatter is None
        assert len(errors) == 1
        assert "YAML" in errors[0]

    def test_empty_frontmatter(self):
        content = """---
---

Body content.
"""
        frontmatter, body, errors = parse_frontmatter(content)

        assert frontmatter == {}
        assert "Body content." in body
        assert len(errors) == 0


class TestExtractMetadata:
    """Tests for extract_metadata function."""

    def test_valid_metadata(self):
        frontmatter = {
            "name": "my-skill",
            "description": "Does something useful",
        }
        metadata, errors = extract_metadata(frontmatter)

        assert metadata is not None
        assert metadata.name == "my-skill"
        assert metadata.description == "Does something useful"
        assert len(errors) == 0

    def test_missing_fields(self):
        frontmatter = {}
        metadata, errors = extract_metadata(frontmatter)

        assert metadata is not None
        assert metadata.name == ""
        assert metadata.description == ""

    def test_none_frontmatter(self):
        metadata, errors = extract_metadata(None)
        assert metadata is None


class TestYAMLCoercionPrevention:
    """Tests that the custom YAML loader prevents implicit type coercion."""

    def test_bool_values_stay_as_strings(self):
        for bool_word in ("yes", "no", "true", "false", "on", "off"):
            content = f"---\nlicense: {bool_word}\nname: test\ndescription: test\n---\nBody"
            frontmatter, _, errors = parse_frontmatter(content)
            assert frontmatter is not None, f"Failed to parse with license: {bool_word}"
            assert frontmatter["license"] == bool_word, (
                f"Expected string '{bool_word}', got {frontmatter['license']!r}"
            )
            assert len(errors) == 0

    def test_null_stays_as_string(self):
        content = "---\nlicense: null\nname: test\ndescription: test\n---\nBody"
        frontmatter, _, errors = parse_frontmatter(content)
        assert frontmatter is not None
        assert frontmatter["license"] == "null"
        assert len(errors) == 0

    def test_empty_value_becomes_empty_string(self):
        content = "---\ncompatibility: \nname: test\ndescription: test\n---\nBody"
        frontmatter, _, errors = parse_frontmatter(content)
        assert frontmatter is not None
        assert frontmatter["compatibility"] == ""
        assert len(errors) == 0

    def test_numbers_still_parse(self):
        content = "---\nname: test\ndescription: test\nmetadata:\n  count: '42'\n---\nBody"
        frontmatter, _, errors = parse_frontmatter(content)
        assert frontmatter is not None
        assert frontmatter["metadata"]["count"] == "42"

    def test_regular_strings_unaffected(self):
        content = "---\nname: my-skill\ndescription: A great skill\nlicense: MIT\n---\nBody"
        frontmatter, _, errors = parse_frontmatter(content)
        assert frontmatter is not None
        assert frontmatter["name"] == "my-skill"
        assert frontmatter["license"] == "MIT"
        assert len(errors) == 0


class TestParseSkill:
    """Tests for parse_skill function."""

    def test_parse_valid_skill(self, valid_skill_path: Path):
        skill = parse_skill(valid_skill_path)

        assert skill.path == valid_skill_path
        assert skill.metadata is not None
        assert skill.metadata.name == "creating-reports"
        assert "Creates detailed reports" in skill.metadata.description
        assert len(skill.body) > 0
        assert len(skill.parse_errors) == 0

    def test_parse_invalid_skill(self, invalid_skill_path: Path):
        skill = parse_skill(invalid_skill_path)

        assert skill.path == invalid_skill_path
        assert skill.metadata is not None
        assert skill.metadata.name == "My_Skill"

    def test_parse_nonexistent_path(self, tmp_path: Path):
        nonexistent = tmp_path / "nonexistent"
        skill = parse_skill(nonexistent)

        assert len(skill.parse_errors) > 0
        assert "does not exist" in skill.parse_errors[0]

    def test_parse_missing_skill_md(self, tmp_path: Path):
        skill = parse_skill(tmp_path)

        assert len(skill.parse_errors) > 0
        assert "SKILL.md" in skill.parse_errors[0]

    def test_detects_subfolders(self, tmp_path: Path):
        # Create skill with subfolders
        (tmp_path / "SKILL.md").write_text("---\nname: test\ndescription: test\n---\nBody")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "references").mkdir()

        skill = parse_skill(tmp_path)

        assert skill.has_scripts
        assert skill.has_references
        assert not skill.has_assets
