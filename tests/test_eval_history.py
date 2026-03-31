"""Tests for evaluation history persistence."""

import json
from pathlib import Path

import pytest

from skill_lab.core.eval_history import (
    EVAL_SCHEMA_VERSION,
    MAX_EVAL_FILES,
    EvalRecord,
    _prune_old_evals,
    _sanitize_timestamp,
    load_eval,
    load_latest_eval,
    save_eval,
)
from skill_lab.core.models import (
    CheckResult,
    EvalDimension,
    EvaluationReport,
    JudgeCriterion,
    JudgeResult,
    Severity,
)


def _make_report(
    score: float = 72.3,
    passed: int = 30,
    total: int = 37,
    timestamp: str = "2026-03-31T14:22:05+00:00",
) -> EvaluationReport:
    """Build a minimal EvaluationReport for testing."""
    results = [
        CheckResult(
            check_id="structure.skill-md-exists",
            check_name="SKILL.md Exists",
            passed=True,
            severity=Severity.HIGH,
            dimension=EvalDimension.STRUCTURE,
            message="SKILL.md found",
        ),
        CheckResult(
            check_id="content.token-budget",
            check_name="Token Budget",
            passed=False,
            severity=Severity.MEDIUM,
            dimension=EvalDimension.CONTENT,
            message="Body exceeds 5,000 token recommendation",
            fix="Reduce body content to under ~5,000 tokens.",
        ),
    ]
    return EvaluationReport(
        skill_path="/tmp/test-skill",
        skill_name="test-skill",
        timestamp=timestamp,
        duration_ms=42.5,
        quality_score=score,
        overall_pass=True,
        checks_run=total,
        checks_passed=passed,
        checks_failed=total - passed,
        results=results,
        summary={"by_dimension": {}},
    )


def _make_judge(score: float = 68.8) -> JudgeResult:
    """Build a minimal JudgeResult for testing."""
    criteria = (
        JudgeCriterion(
            id="intent_clarity",
            name="Intent Clarity",
            axis="activation",
            score=3,
            reasoning="Clear description.",
        ),
        JudgeCriterion(
            id="trigger_coverage",
            name="Trigger Coverage",
            axis="activation",
            score=2,
            reasoning="Missing implicit triggers.",
        ),
    )
    return JudgeResult(
        criteria=criteria,
        activation_score=62.5,
        instruction_score=75.0,
        judge_score=score,
        verdict="Needs work",
        suggestions=("Add trigger phrases.", "Improve error handling."),
    )


# =============================================================================
# save_eval
# =============================================================================


class TestSaveEval:
    def test_creates_evals_directory(self, tmp_path: Path) -> None:
        report = _make_report()
        save_eval(tmp_path, report)
        assert (tmp_path / ".sklab" / "evals").is_dir()

    def test_writes_json_file(self, tmp_path: Path) -> None:
        report = _make_report()
        path = save_eval(tmp_path, report)
        assert path.exists()
        assert path.suffix == ".json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_filename_is_timestamp_based(self, tmp_path: Path) -> None:
        report = _make_report(timestamp="2026-03-31T14:22:05+00:00")
        path = save_eval(tmp_path, report)
        assert "2026-03-31T14-22-05" in path.name

    def test_schema_version_present(self, tmp_path: Path) -> None:
        report = _make_report()
        path = save_eval(tmp_path, report)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["schema_version"] == EVAL_SCHEMA_VERSION

    def test_includes_full_check_results(self, tmp_path: Path) -> None:
        report = _make_report()
        path = save_eval(tmp_path, report)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data["results"]) == 2
        assert data["results"][0]["check_id"] == "structure.skill-md-exists"
        assert data["results"][1]["fix"] == "Reduce body content to under ~5,000 tokens."

    def test_judge_null_when_absent(self, tmp_path: Path) -> None:
        report = _make_report()
        path = save_eval(tmp_path, report)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["judge"] is None

    def test_includes_judge_when_present(self, tmp_path: Path) -> None:
        report = _make_report()
        judge = _make_judge()
        path = save_eval(
            tmp_path,
            report,
            judge_result=judge,
            judge_model="claude-haiku-4-5-20251001",
            judge_usage={"input_tokens": 1200, "output_tokens": 450},
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["judge"] is not None
        assert data["judge"]["judge_score"] == 68.8
        assert data["judge"]["model"] == "claude-haiku-4-5-20251001"
        assert data["judge"]["usage"]["input_tokens"] == 1200
        assert len(data["judge"]["criteria"]) == 2
        assert data["judge"]["suggestions"] == [
            "Add trigger phrases.",
            "Improve error handling.",
        ]


# =============================================================================
# _prune_old_evals
# =============================================================================


class TestPruneOldEvals:
    def test_prunes_oldest_beyond_max(self, tmp_path: Path) -> None:
        evals_dir = tmp_path / ".sklab" / "evals"
        evals_dir.mkdir(parents=True)
        for i in range(25):
            (evals_dir / f"2026-03-{i:02d}T00-00-00.json").write_text("{}")
        _prune_old_evals(evals_dir, max_files=20)
        remaining = list(evals_dir.glob("*.json"))
        assert len(remaining) == 20

    def test_no_prune_under_limit(self, tmp_path: Path) -> None:
        evals_dir = tmp_path / ".sklab" / "evals"
        evals_dir.mkdir(parents=True)
        for i in range(5):
            (evals_dir / f"2026-03-{i:02d}T00-00-00.json").write_text("{}")
        _prune_old_evals(evals_dir, max_files=20)
        remaining = list(evals_dir.glob("*.json"))
        assert len(remaining) == 5

    def test_correct_files_deleted(self, tmp_path: Path) -> None:
        evals_dir = tmp_path / ".sklab" / "evals"
        evals_dir.mkdir(parents=True)
        for i in range(5):
            (evals_dir / f"2026-03-{i:02d}T00-00-00.json").write_text("{}")
        _prune_old_evals(evals_dir, max_files=3)
        remaining = sorted(f.name for f in evals_dir.glob("*.json"))
        assert remaining == [
            "2026-03-02T00-00-00.json",
            "2026-03-03T00-00-00.json",
            "2026-03-04T00-00-00.json",
        ]


# =============================================================================
# load_latest_eval
# =============================================================================


class TestLoadLatestEval:
    def test_returns_none_when_dir_missing(self, tmp_path: Path) -> None:
        assert load_latest_eval(tmp_path) is None

    def test_returns_none_when_empty(self, tmp_path: Path) -> None:
        evals_dir = tmp_path / ".sklab" / "evals"
        evals_dir.mkdir(parents=True)
        assert load_latest_eval(tmp_path) is None

    def test_returns_latest_file(self, tmp_path: Path) -> None:
        report_old = _make_report(score=60.0, timestamp="2026-03-01T10:00:00+00:00")
        report_new = _make_report(score=80.0, timestamp="2026-03-02T10:00:00+00:00")
        save_eval(tmp_path, report_old)
        save_eval(tmp_path, report_new)
        record = load_latest_eval(tmp_path)
        assert record is not None
        assert record.report.quality_score == 80.0

    def test_roundtrip_save_load_static_only(self, tmp_path: Path) -> None:
        report = _make_report()
        save_eval(tmp_path, report)
        record = load_latest_eval(tmp_path)
        assert record is not None
        assert record.schema_version == EVAL_SCHEMA_VERSION
        assert record.report.quality_score == 72.3
        assert record.report.checks_passed == 30
        assert len(record.report.results) == 2
        assert record.report.results[0].check_id == "structure.skill-md-exists"
        assert record.report.results[1].passed is False
        assert record.report.results[1].fix == "Reduce body content to under ~5,000 tokens."
        assert record.judge is None

    def test_roundtrip_save_load_with_judge(self, tmp_path: Path) -> None:
        report = _make_report()
        judge = _make_judge()
        usage = {"input_tokens": 1200, "output_tokens": 450, "total_tokens": 1650}
        save_eval(
            tmp_path,
            report,
            judge_result=judge,
            judge_model="claude-haiku-4-5-20251001",
            judge_usage=usage,
        )
        record = load_latest_eval(tmp_path)
        assert record is not None
        assert record.judge is not None
        assert record.judge.judge_score == 68.8
        assert record.judge.verdict == "Needs work"
        assert len(record.judge.criteria) == 2
        assert record.judge.criteria[0].id == "intent_clarity"
        assert record.judge.criteria[0].score == 3
        assert record.judge.suggestions == ("Add trigger phrases.", "Improve error handling.")
        assert record.judge_model == "claude-haiku-4-5-20251001"
        assert record.judge_usage is not None
        assert record.judge_usage["input_tokens"] == 1200


# =============================================================================
# load_eval (error cases)
# =============================================================================


class TestLoadEval:
    def test_raises_on_corrupt_json(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "corrupt.json"
        bad_file.write_text("not valid json {{{")
        with pytest.raises(ValueError, match="Cannot read eval file"):
            load_eval(bad_file)

    def test_raises_on_non_object(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "array.json"
        bad_file.write_text("[]")
        with pytest.raises(ValueError, match="expected JSON object"):
            load_eval(bad_file)


# =============================================================================
# _sanitize_timestamp
# =============================================================================


class TestSanitizeTimestamp:
    def test_replaces_colons(self) -> None:
        assert _sanitize_timestamp("2026-03-31T14:22:05+00:00") == "2026-03-31T14-22-05+00-00"

    def test_no_change_without_colons(self) -> None:
        assert _sanitize_timestamp("2026-03-31") == "2026-03-31"
