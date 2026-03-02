"""Tests for prompt exporter module."""

import json

from skill_lab.exporters.prompt_exporter import render_json, render_markdown, render_xml

SAMPLE_SKILLS = [
    {
        "name": "my-skill",
        "description": "Does a thing",
        "location": "/abs/path/to/my-skill",
    },
    {
        "name": "other-skill",
        "description": "Does another thing",
        "location": "/abs/path/to/other-skill",
    },
]


class TestRenderXml:
    """Tests for XML rendering."""

    def test_single_skill(self):
        result = render_xml(SAMPLE_SKILLS[:1])
        assert "<available_skills>" in result
        assert "<name>my-skill</name>" in result
        assert "<description>Does a thing</description>" in result
        assert "<location>/abs/path/to/my-skill</location>" in result
        assert "</available_skills>" in result

    def test_multiple_skills(self):
        result = render_xml(SAMPLE_SKILLS)
        assert result.count("<skill>") == 2
        assert "my-skill" in result
        assert "other-skill" in result

    def test_html_escaping(self):
        skills = [{"name": "test", "description": '<script>alert("xss")</script>', "location": "/path"}]
        result = render_xml(skills)
        assert "&lt;script&gt;" in result
        assert "&quot;" in result

    def test_empty_list(self):
        result = render_xml([])
        assert "<available_skills>" in result
        assert "</available_skills>" in result
        assert "<skill>" not in result


class TestRenderMarkdown:
    """Tests for Markdown rendering."""

    def test_single_skill(self):
        result = render_markdown(SAMPLE_SKILLS[:1])
        assert "## Available Skills" in result
        assert "### my-skill" in result
        assert "**Description:** Does a thing" in result
        assert "**Location:** `/abs/path/to/my-skill`" in result

    def test_multiple_skills(self):
        result = render_markdown(SAMPLE_SKILLS)
        assert result.count("###") == 2


class TestRenderJson:
    """Tests for JSON rendering."""

    def test_single_skill(self):
        result = render_json(SAMPLE_SKILLS[:1])
        data = json.loads(result)
        assert "available_skills" in data
        assert len(data["available_skills"]) == 1
        assert data["available_skills"][0]["name"] == "my-skill"

    def test_multiple_skills(self):
        result = render_json(SAMPLE_SKILLS)
        data = json.loads(result)
        assert len(data["available_skills"]) == 2

    def test_valid_json(self):
        result = render_json(SAMPLE_SKILLS)
        # Should not raise
        json.loads(result)
