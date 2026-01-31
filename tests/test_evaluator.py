"""Tests for static evaluator."""

from pathlib import Path

from skill_lab.evaluators.static_evaluator import StaticEvaluator


class TestStaticEvaluator:
    """Tests for StaticEvaluator class."""

    def test_evaluate_valid_skill(self, evaluator: StaticEvaluator, valid_skill_path: Path):
        report = evaluator.evaluate(valid_skill_path)

        assert Path(report.skill_path) == valid_skill_path
        assert report.skill_name == "creating-reports"
        assert report.checks_run > 0
        assert report.quality_score > 0
        assert report.timestamp
        assert report.duration_ms >= 0

    def test_evaluate_invalid_skill(self, evaluator: StaticEvaluator, invalid_skill_path: Path):
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

    def test_validate_valid_skill(self, evaluator: StaticEvaluator, valid_skill_path: Path):
        passed, errors = evaluator.validate(valid_skill_path)

        assert passed
        assert len(errors) == 0

    def test_validate_invalid_skill(self, evaluator: StaticEvaluator, invalid_skill_path: Path):
        passed, errors = evaluator.validate(invalid_skill_path)

        assert not passed
        assert len(errors) > 0

    def test_report_to_dict(self, evaluator: StaticEvaluator, valid_skill_path: Path):
        report = evaluator.evaluate(valid_skill_path)

        report_dict = report.to_dict()

        assert isinstance(report_dict, dict)
        assert "skill_path" in report_dict
        assert "quality_score" in report_dict
        assert "results" in report_dict
        assert isinstance(report_dict["results"], list)

    def test_evaluate_spec_only(self, valid_skill_path: Path):
        """Test that spec_only mode only runs spec-required checks."""
        evaluator = StaticEvaluator(spec_only=True)
        report = evaluator.evaluate(valid_skill_path)

        # Should only run 10 spec-required checks
        assert report.checks_run == 10

        # All results should be from spec-required checks
        spec_required_ids = {
            "structure.skill-md-exists",
            "structure.valid-frontmatter",
            "frontmatter.compatibility-length",
            "frontmatter.metadata-format",
            "naming.required",
            "naming.format",
            "naming.matches-directory",
            "description.required",
            "description.not-empty",
            "description.max-length",
        }
        result_ids = {r.check_id for r in report.results}
        assert result_ids == spec_required_ids

    def test_evaluate_all_checks(self, valid_skill_path: Path):
        """Test that default mode runs all checks including quality suggestions."""
        evaluator = StaticEvaluator(spec_only=False)
        report = evaluator.evaluate(valid_skill_path)

        # Should run all 18 checks
        assert report.checks_run == 18
