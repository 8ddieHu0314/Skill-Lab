"""Tests for CLI interface."""

import json
import os
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
    """Tests for the check command."""

    def test_validate_valid_skill(self, valid_skill_path: Path):
        result = runner.invoke(app, ["check", str(valid_skill_path)])
        assert result.exit_code == 0
        assert "passed" in result.stdout.lower()

    def test_validate_invalid_skill(self, invalid_skill_path: Path):
        result = runner.invoke(app, ["check", str(invalid_skill_path)])
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
        assert "Front-loaded" in result.stdout

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
        result = runner.invoke(app, ["prompt", str(valid_skill_path), str(minimal_skill_path)])
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


class TestCacheIsWarm:
    """Tests for _cache_is_warm helper."""

    def test_no_traces_dir(self, tmp_path: Path) -> None:
        from skill_lab.commands.trigger import _cache_is_warm

        assert _cache_is_warm(tmp_path) is False

    def test_empty_traces_dir(self, tmp_path: Path) -> None:
        from skill_lab.commands.trigger import _cache_is_warm

        (tmp_path / ".sklab" / "traces").mkdir(parents=True)
        assert _cache_is_warm(tmp_path) is False

    def test_recent_trace_is_warm(self, tmp_path: Path) -> None:
        from skill_lab.commands.trigger import _cache_is_warm

        traces = tmp_path / ".sklab" / "traces"
        traces.mkdir(parents=True)
        (traces / "test.jsonl").write_text("{}")
        assert _cache_is_warm(tmp_path) is True

    def test_old_trace_is_cold(self, tmp_path: Path) -> None:
        import os
        import time

        from skill_lab.commands.trigger import _cache_is_warm

        traces = tmp_path / ".sklab" / "traces"
        traces.mkdir(parents=True)
        trace_file = traces / "test.jsonl"
        trace_file.write_text("{}")
        # Set mtime to 10 minutes ago
        old_time = time.time() - 600
        os.utime(trace_file, (old_time, old_time))
        assert _cache_is_warm(tmp_path) is False


class TestBanner:
    """Tests for the ASCII banner."""

    def test_banner_wide_terminal(self):
        """Banner renders ASCII art on wide terminals."""
        from unittest.mock import PropertyMock, patch

        from skill_lab.cli import _print_banner, console

        with patch.object(type(console), "width", new_callable=PropertyMock, return_value=120):
            _print_banner()  # should not raise

    def test_banner_narrow_terminal_fallback(self):
        """Narrow terminals get a plain-text fallback instead of ASCII art."""
        from io import StringIO
        from unittest.mock import PropertyMock, patch

        from rich.console import Console

        from skill_lab import cli

        buf = StringIO()
        narrow_console = Console(file=buf, width=50)
        original = cli.console
        cli.console = narrow_console
        try:
            with patch.object(
                type(narrow_console), "width", new_callable=PropertyMock, return_value=50
            ):
                cli._print_banner()
            output = buf.getvalue()
            assert "SKILL LAB" in output
            # Should NOT contain box-drawing characters from the ASCII art
            assert "███" not in output
        finally:
            cli.console = original


class TestDotenvLoading:
    """Tests for .env file loading."""

    def test_env_file_loads_api_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """API keys from .env file are available to commands."""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=test-key-from-dotenv\n")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_file, override=False)

        assert os.environ.get("ANTHROPIC_API_KEY") == "test-key-from-dotenv"

    def test_real_env_overrides_dotenv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Real environment variables take precedence over .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=from-dotenv\n")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "from-real-env")

        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_file, override=False)

        assert os.environ.get("ANTHROPIC_API_KEY") == "from-real-env"

    def test_missing_env_file_is_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing .env file does not cause errors."""
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=tmp_path / ".env", override=False)  # should not raise
