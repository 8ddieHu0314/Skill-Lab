"""Tests for CLI interface."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skill_lab.cli import app

runner = CliRunner()


class TestEvaluateCommand:
    """Tests for the evaluate command."""

    def test_evaluate_valid_skill(self, valid_skill_path: Path):
        result = runner.invoke(app, ["evaluate", str(valid_skill_path)])
        assert result.exit_code == 0
        assert "Quality Score" in result.stdout

    def test_evaluate_invalid_skill(self, invalid_skill_path: Path):
        result = runner.invoke(app, ["evaluate", str(invalid_skill_path)])
        # Invalid skill should have non-zero exit code
        assert result.exit_code == 1

    def test_evaluate_json_format(self, valid_skill_path: Path):
        result = runner.invoke(app, ["evaluate", str(valid_skill_path), "--format", "json"])
        assert result.exit_code == 0
        assert '"quality_score"' in result.stdout
        assert '"skill_path"' in result.stdout

    def test_evaluate_verbose(self, valid_skill_path: Path):
        result = runner.invoke(app, ["evaluate", str(valid_skill_path), "--verbose"])
        assert result.exit_code == 0
        # Verbose should show all checks
        assert "Check Results" in result.stdout

    def test_evaluate_nonexistent_path(self, tmp_path: Path):
        nonexistent = tmp_path / "nonexistent"
        result = runner.invoke(app, ["evaluate", str(nonexistent)])
        # Should fail because path doesn't exist
        assert result.exit_code != 0


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_skill(self, valid_skill_path: Path):
        result = runner.invoke(app, ["validate", str(valid_skill_path)])
        assert result.exit_code == 0
        assert "passed" in result.stdout.lower()

    def test_validate_invalid_skill(self, invalid_skill_path: Path):
        result = runner.invoke(app, ["validate", str(invalid_skill_path)])
        assert result.exit_code == 1
        assert "failed" in result.stdout.lower()


class TestListChecksCommand:
    """Tests for the list-checks command."""

    def test_list_all_checks(self):
        result = runner.invoke(app, ["list-checks"])
        assert result.exit_code == 0
        # Check for partial check IDs (table may truncate long IDs)
        assert "structure" in result.stdout
        assert "naming" in result.stdout
        assert "description" in result.stdout
        assert "content" in result.stdout
        assert "Total:" in result.stdout

    def test_list_checks_by_dimension(self):
        result = runner.invoke(app, ["list-checks", "--dimension", "structure"])
        assert result.exit_code == 0
        assert "structure." in result.stdout
        # Should not contain checks from other dimensions
        assert "naming.required" not in result.stdout

    def test_list_checks_invalid_dimension(self):
        result = runner.invoke(app, ["list-checks", "--dimension", "invalid"])
        assert result.exit_code == 1
        assert "Invalid dimension" in result.stdout


class TestInfoCommand:
    """Tests for the info command."""

    def test_info_rich_panel(self, valid_skill_path: Path):
        result = runner.invoke(app, ["info", str(valid_skill_path)])
        assert result.exit_code == 0
        assert "creating-reports" in result.stdout
        assert "Tokens (estimated)" in result.stdout
        assert "Discovery" in result.stdout
        assert "Activation" in result.stdout

    def test_info_json(self, valid_skill_path: Path):
        result = runner.invoke(app, ["info", str(valid_skill_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["name"] == "creating-reports"
        assert "tokens" in data
        assert "discovery" in data["tokens"]
        assert "activation" in data["tokens"]

    def test_info_field_name(self, valid_skill_path: Path):
        result = runner.invoke(app, ["info", str(valid_skill_path), "--field", "name"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "creating-reports"

    def test_info_field_tokens(self, valid_skill_path: Path):
        result = runner.invoke(app, ["info", str(valid_skill_path), "--field", "tokens"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "discovery" in data
        assert "activation" in data

    def test_info_field_unknown(self, valid_skill_path: Path):
        result = runner.invoke(app, ["info", str(valid_skill_path), "--field", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown field" in result.stdout

    def test_info_nonexistent_path(self, tmp_path: Path):
        nonexistent = tmp_path / "nonexistent"
        result = runner.invoke(app, ["info", str(nonexistent)])
        assert result.exit_code != 0


class TestPromptCommand:
    """Tests for the prompt command."""

    def test_prompt_xml_default(self, valid_skill_path: Path):
        result = runner.invoke(app, ["prompt", str(valid_skill_path)])
        assert result.exit_code == 0
        assert "<available_skills>" in result.stdout
        assert "<name>creating-reports</name>" in result.stdout
        assert "</available_skills>" in result.stdout

    def test_prompt_markdown(self, valid_skill_path: Path):
        result = runner.invoke(app, ["prompt", str(valid_skill_path), "-f", "markdown"])
        assert result.exit_code == 0
        assert "## Available Skills" in result.stdout
        assert "### creating-reports" in result.stdout

    def test_prompt_json(self, valid_skill_path: Path):
        result = runner.invoke(app, ["prompt", str(valid_skill_path), "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "available_skills" in data
        assert data["available_skills"][0]["name"] == "creating-reports"

    def test_prompt_multiple_skills(self, valid_skill_path: Path, minimal_skill_path: Path):
        result = runner.invoke(
            app, ["prompt", str(valid_skill_path), str(minimal_skill_path)]
        )
        assert result.exit_code == 0
        assert "creating-reports" in result.stdout
        assert "testing-features" in result.stdout

    def test_prompt_invalid_format(self, valid_skill_path: Path):
        result = runner.invoke(app, ["prompt", str(valid_skill_path), "-f", "csv"])
        assert result.exit_code == 1
        assert "Invalid format" in result.stdout

    def test_prompt_xml_escapes_html(self, tmp_path: Path):
        """XML output escapes special characters."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: test-skill\ndescription: Uses <tags> & "quotes"\n---\nBody'
        )
        result = runner.invoke(app, ["prompt", str(skill_dir)])
        assert result.exit_code == 0
        assert "&lt;tags&gt;" in result.stdout
        assert "&amp;" in result.stdout


class TestTriggerCommand:
    """Tests for the trigger command."""

    def test_trigger_no_tests_hints_generate(self, invalid_skill_path: Path):
        """Test that trigger command hints at sklab generate when no tests exist."""
        result = runner.invoke(app, ["trigger", str(invalid_skill_path)])
        assert result.exit_code == 1
        assert "No trigger tests found" in result.stdout
        assert "sklab generate" in result.stdout
