"""Tests for trace check YAML loader."""

from pathlib import Path

import pytest

from skill_lab.core.models import TraceCheckDefinition
from skill_lab.tracechecks.trace_check_loader import load_trace_checks


class TestTraceCheckLoader:
    """Tests for the trace check YAML loader."""

    def test_load_valid_trace_checks(self, valid_skill_path: Path):
        """Test loading valid trace checks from YAML."""
        checks = load_trace_checks(valid_skill_path)

        assert len(checks) == 4
        assert all(isinstance(c, TraceCheckDefinition) for c in checks)

    def test_load_check_fields(self, valid_skill_path: Path):
        """Test that check fields are parsed correctly."""
        checks = load_trace_checks(valid_skill_path)

        # Find the command_presence check
        cmd_check = next(c for c in checks if c.id == "npm-install-ran")
        assert cmd_check.type == "command_presence"
        assert cmd_check.pattern == "npm install"
        assert cmd_check.description == "Verify npm install was executed"

        # Find the event_sequence check
        seq_check = next(c for c in checks if c.id == "correct-build-sequence")
        assert seq_check.type == "event_sequence"
        assert seq_check.sequence == ("npm init", "npm install", "npm run build")

        # Find the loop_detection check
        loop_check = next(c for c in checks if c.id == "no-excessive-retries")
        assert loop_check.type == "loop_detection"
        assert loop_check.max_retries == 3

        # Find the efficiency check
        eff_check = next(c for c in checks if c.id == "efficient-execution")
        assert eff_check.type == "efficiency"
        assert eff_check.max_commands == 20

    def test_load_missing_file_raises(self, tmp_path: Path):
        """Test that missing trace_checks.yaml raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_trace_checks(tmp_path)

    def test_load_empty_file_raises(self, tmp_path: Path):
        """Test that empty YAML file raises ValueError."""
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "trace_checks.yaml").write_text("")

        with pytest.raises(ValueError, match="Empty trace checks file"):
            load_trace_checks(tmp_path)

    def test_load_no_checks_raises(self, tmp_path: Path):
        """Test that YAML without checks key raises ValueError."""
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "trace_checks.yaml").write_text("other_key: value")

        with pytest.raises(ValueError, match="No checks defined"):
            load_trace_checks(tmp_path)

    def test_load_missing_id_raises(self, tmp_path: Path):
        """Test that check without id raises ValueError."""
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "trace_checks.yaml").write_text(
            "checks:\n  - type: command_presence\n    pattern: test"
        )

        with pytest.raises(ValueError, match="missing required 'id' field"):
            load_trace_checks(tmp_path)

    def test_load_missing_type_raises(self, tmp_path: Path):
        """Test that check without type raises ValueError."""
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "trace_checks.yaml").write_text(
            "checks:\n  - id: test-check"
        )

        with pytest.raises(ValueError, match="missing required 'type' field"):
            load_trace_checks(tmp_path)

    def test_load_invalid_type_raises(self, tmp_path: Path):
        """Test that check with invalid type raises ValueError."""
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "trace_checks.yaml").write_text(
            "checks:\n  - id: test-check\n    type: invalid_type"
        )

        with pytest.raises(ValueError, match="invalid type 'invalid_type'"):
            load_trace_checks(tmp_path)
