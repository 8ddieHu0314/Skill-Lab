"""Tests for CLI interface."""

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
