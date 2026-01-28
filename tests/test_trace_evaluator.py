"""Tests for trace evaluator."""

from pathlib import Path

import pytest

from skill_lab.evaluators.trace_evaluator import TraceEvaluator


class TestTraceEvaluator:
    """Tests for TraceEvaluator class."""

    def test_evaluate_valid_trace(
        self,
        trace_evaluator: TraceEvaluator,
        valid_skill_path: Path,
        sample_trace_path: Path,
    ):
        """Test evaluating a valid trace against trace checks."""
        report = trace_evaluator.evaluate(valid_skill_path, sample_trace_path)

        assert report.trace_path == str(sample_trace_path)
        assert report.project_dir == str(valid_skill_path)
        assert report.checks_run == 4
        assert report.timestamp
        assert report.duration_ms >= 0

    def test_evaluate_all_checks_pass(
        self,
        trace_evaluator: TraceEvaluator,
        valid_skill_path: Path,
        sample_trace_path: Path,
    ):
        """Test that all checks pass for the sample trace."""
        report = trace_evaluator.evaluate(valid_skill_path, sample_trace_path)

        assert report.overall_pass
        assert report.checks_passed == report.checks_run
        assert report.checks_failed == 0
        assert report.pass_rate == 100.0

    def test_evaluate_missing_trace_file(
        self,
        trace_evaluator: TraceEvaluator,
        valid_skill_path: Path,
        tmp_path: Path,
    ):
        """Test that missing trace file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            trace_evaluator.evaluate(valid_skill_path, tmp_path / "nonexistent.jsonl")

    def test_evaluate_missing_checks_file(
        self,
        trace_evaluator: TraceEvaluator,
        sample_trace_path: Path,
        tmp_path: Path,
    ):
        """Test that missing trace_checks.yaml raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            trace_evaluator.evaluate(tmp_path, sample_trace_path)

    def test_report_to_dict(
        self,
        trace_evaluator: TraceEvaluator,
        valid_skill_path: Path,
        sample_trace_path: Path,
    ):
        """Test that report can be serialized to dict."""
        report = trace_evaluator.evaluate(valid_skill_path, sample_trace_path)
        report_dict = report.to_dict()

        assert isinstance(report_dict, dict)
        assert "trace_path" in report_dict
        assert "project_dir" in report_dict
        assert "checks_run" in report_dict
        assert "results" in report_dict
        assert isinstance(report_dict["results"], list)

    def test_report_summary_by_type(
        self,
        trace_evaluator: TraceEvaluator,
        valid_skill_path: Path,
        sample_trace_path: Path,
    ):
        """Test that report contains summary by check type."""
        report = trace_evaluator.evaluate(valid_skill_path, sample_trace_path)

        assert "by_type" in report.summary
        by_type = report.summary["by_type"]

        # Should have entries for each check type used
        assert "command_presence" in by_type
        assert "event_sequence" in by_type
        assert "loop_detection" in by_type
        assert "efficiency" in by_type

        # Each entry should have passed/failed/total counts
        for type_name, stats in by_type.items():
            assert "passed" in stats
            assert "failed" in stats
            assert "total" in stats
            assert stats["total"] == stats["passed"] + stats["failed"]


class TestTraceEvaluatorWithFailures:
    """Tests for trace evaluator with failing checks."""

    def test_evaluate_with_failing_checks(self, trace_evaluator: TraceEvaluator, tmp_path: Path):
        """Test evaluation when some checks fail."""
        # Create a skill with trace checks that will fail
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "trace_checks.yaml").write_text("""
checks:
  - id: missing-command
    type: command_presence
    pattern: "yarn deploy"

  - id: simple-check
    type: command_presence
    pattern: "npm"
""")

        # Create a simple trace
        trace_file = tmp_path / "trace.jsonl"
        trace_file.write_text(
            '{"type": "item.completed", "item": {"type": "command_execution"}, "command": "npm install"}\n'
        )

        report = trace_evaluator.evaluate(tmp_path, trace_file)

        assert not report.overall_pass
        assert report.checks_failed == 1
        assert report.checks_passed == 1

        # Check specific results
        failing = [r for r in report.results if not r.passed]
        assert len(failing) == 1
        assert failing[0].check_id == "missing-command"
