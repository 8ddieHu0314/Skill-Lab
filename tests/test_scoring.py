"""Tests for scoring module."""

import pytest

from skill_lab.core.models import CheckResult, EvalDimension, Severity
from skill_lab.core.scoring import (
    build_summary,
    calculate_dimension_score,
    calculate_score,
)


def make_result(
    passed: bool,
    severity: Severity = Severity.ERROR,
    dimension: EvalDimension = EvalDimension.STRUCTURE,
) -> CheckResult:
    """Helper to create a CheckResult for testing."""
    return CheckResult(
        check_id="test.check",
        check_name="Test Check",
        passed=passed,
        severity=severity,
        dimension=dimension,
        message="Test message",
    )


class TestCalculateDimensionScore:
    """Tests for calculate_dimension_score function."""

    def test_all_passed(self):
        results = [
            make_result(passed=True, severity=Severity.ERROR),
            make_result(passed=True, severity=Severity.WARNING),
        ]
        score = calculate_dimension_score(results)
        assert score == 100.0

    def test_all_failed(self):
        results = [
            make_result(passed=False, severity=Severity.ERROR),
            make_result(passed=False, severity=Severity.WARNING),
        ]
        score = calculate_dimension_score(results)
        assert score == 0.0

    def test_mixed_results(self):
        results = [
            make_result(passed=True, severity=Severity.ERROR),
            make_result(passed=False, severity=Severity.ERROR),
        ]
        score = calculate_dimension_score(results)
        assert score == 50.0

    def test_empty_results(self):
        score = calculate_dimension_score([])
        assert score == 100.0

    def test_severity_weighting(self):
        # One failed error (weight 1.0) and one passed warning (weight 0.5)
        # Total weight = 1.5, passed weight = 0.5
        # Score = 0.5 / 1.5 * 100 = 33.33
        results = [
            make_result(passed=False, severity=Severity.ERROR),
            make_result(passed=True, severity=Severity.WARNING),
        ]
        score = calculate_dimension_score(results)
        assert 33.0 <= score <= 34.0


class TestCalculateScore:
    """Tests for calculate_score function."""

    def test_perfect_score(self):
        results = [
            make_result(passed=True, dimension=EvalDimension.STRUCTURE),
            make_result(passed=True, dimension=EvalDimension.NAMING),
            make_result(passed=True, dimension=EvalDimension.DESCRIPTION),
            make_result(passed=True, dimension=EvalDimension.CONTENT),
        ]
        score = calculate_score(results)
        assert score == 100.0

    def test_zero_score(self):
        results = [
            make_result(passed=False, dimension=EvalDimension.STRUCTURE),
            make_result(passed=False, dimension=EvalDimension.NAMING),
            make_result(passed=False, dimension=EvalDimension.DESCRIPTION),
            make_result(passed=False, dimension=EvalDimension.CONTENT),
        ]
        score = calculate_score(results)
        assert score == 0.0

    def test_empty_results(self):
        score = calculate_score([])
        assert score == 100.0


class TestBuildSummary:
    """Tests for build_summary function."""

    def test_summary_structure(self):
        results = [
            make_result(passed=True, severity=Severity.ERROR, dimension=EvalDimension.STRUCTURE),
            make_result(passed=False, severity=Severity.WARNING, dimension=EvalDimension.NAMING),
        ]
        summary = build_summary(results)

        assert "by_severity" in summary
        assert "by_dimension" in summary

        assert summary["by_severity"]["error"]["passed"] == 1
        assert summary["by_severity"]["error"]["failed"] == 0
        assert summary["by_severity"]["warning"]["passed"] == 0
        assert summary["by_severity"]["warning"]["failed"] == 1

        assert summary["by_dimension"]["structure"]["passed"] == 1
        assert summary["by_dimension"]["naming"]["failed"] == 1

    def test_empty_results(self):
        summary = build_summary([])
        assert all(
            counts["passed"] == 0 and counts["failed"] == 0
            for counts in summary["by_severity"].values()
        )
