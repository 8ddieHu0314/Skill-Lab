"""Tests for static evaluator."""

from pathlib import Path

import pytest

from agent_skills_eval.evaluators.static_evaluator import StaticEvaluator


class TestStaticEvaluator:
    """Tests for StaticEvaluator class."""

    def test_evaluate_valid_skill(self, valid_skill_path: Path):
        evaluator = StaticEvaluator()
        report = evaluator.evaluate(valid_skill_path)

        assert report.skill_path == str(valid_skill_path)
        assert report.skill_name == "creating-reports"
        assert report.checks_run > 0
        assert report.quality_score > 0
        assert report.timestamp
        assert report.duration_ms >= 0

    def test_evaluate_invalid_skill(self, invalid_skill_path: Path):
        evaluator = StaticEvaluator()
        report = evaluator.evaluate(invalid_skill_path)

        assert not report.overall_pass
        assert report.checks_failed > 0

    def test_evaluate_with_specific_checks(self, valid_skill_path: Path):
        evaluator = StaticEvaluator(check_ids=["structure.skill-md-exists", "naming.required"])
        report = evaluator.evaluate(valid_skill_path)

        assert report.checks_run == 2
        assert all(
            r.check_id in ["structure.skill-md-exists", "naming.required"]
            for r in report.results
        )

    def test_validate_valid_skill(self, valid_skill_path: Path):
        evaluator = StaticEvaluator()
        passed, errors = evaluator.validate(valid_skill_path)

        assert passed
        assert len(errors) == 0

    def test_validate_invalid_skill(self, invalid_skill_path: Path):
        evaluator = StaticEvaluator()
        passed, errors = evaluator.validate(invalid_skill_path)

        assert not passed
        assert len(errors) > 0

    def test_report_to_dict(self, valid_skill_path: Path):
        evaluator = StaticEvaluator()
        report = evaluator.evaluate(valid_skill_path)

        report_dict = report.to_dict()

        assert isinstance(report_dict, dict)
        assert "skill_path" in report_dict
        assert "quality_score" in report_dict
        assert "results" in report_dict
        assert isinstance(report_dict["results"], list)
