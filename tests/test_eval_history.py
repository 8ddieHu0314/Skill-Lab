"""Tests for evaluation history persistence."""

import json
from pathlib import Path

import pytest

from skill_lab.core.eval_history import (
    EVAL_SCHEMA_VERSION,
    _prune_old_evals,
    _sanitize_timestamp,
    load_eval,
    load_latest_eval,
    save_eval,
)
from tests.conftest import make_judge, make_report

# =============================================================================
# save_eval
# =============================================================================


class TestSaveEval:
    def test_creates_evals_directory(self, tmp_path: Path) -> None:
        report = make_report()
        save_eval(tmp_path, report)
        assert (tmp_path / ".sklab" / "evals").is_dir()

    def test_writes_json_file(self, tmp_path: Path) -> None:
        report = make_report()
        path = save_eval(tmp_path, report)
        assert path.exists()
        assert path.suffix == ".json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_filename_is_timestamp_based(self, tmp_path: Path) -> None:
        report = make_report(timestamp="2026-03-31T14:22:05+00:00")
        path = save_eval(tmp_path, report)
        assert "2026-03-31T14-22-05" in path.name

    def test_schema_version_present(self, tmp_path: Path) -> None:
        report = make_report()
        path = save_eval(tmp_path, report)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["schema_version"] == EVAL_SCHEMA_VERSION

    def test_includes_full_check_results(self, tmp_path: Path) -> None:
        report = make_report()
        path = save_eval(tmp_path, report)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data["results"]) == 2
        assert data["results"][0]["check_id"] == "structure.skill-md-exists"
        assert data["results"][1]["fix"] == "Reduce body content to under ~5,000 tokens."

    def test_judge_null_when_absent(self, tmp_path: Path) -> None:
        report = make_report()
        path = save_eval(tmp_path, report)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["judge"] is None

    def test_includes_judge_when_present(self, tmp_path: Path) -> None:
        report = make_report()
        judge = make_judge()
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
        report_old = make_report(score=60.0, timestamp="2026-03-01T10:00:00+00:00")
        report_new = make_report(score=80.0, timestamp="2026-03-02T10:00:00+00:00")
        save_eval(tmp_path, report_old)
        save_eval(tmp_path, report_new)
        record = load_latest_eval(tmp_path)
        assert record is not None
        assert record.report.quality_score == 80.0

    def test_returns_latest_across_timezones(self, tmp_path: Path) -> None:
        """Chronologically later eval is returned even when its local time looks earlier."""
        # 23:50 NZST (+12) = 11:50 UTC (earlier)
        report_old = make_report(score=60.0, timestamp="2026-03-31T23:50:00+12:00")
        # 08:00 EST (-05) = 13:00 UTC (later)
        report_new = make_report(score=80.0, timestamp="2026-03-31T08:00:00-05:00")
        save_eval(tmp_path, report_old)
        save_eval(tmp_path, report_new)
        record = load_latest_eval(tmp_path)
        assert record is not None
        assert record.report.quality_score == 80.0

    def test_roundtrip_save_load_static_only(self, tmp_path: Path) -> None:
        report = make_report()
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
        report = make_report()
        judge = make_judge()
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
    def test_utc_timestamp_unchanged(self) -> None:
        assert _sanitize_timestamp("2026-03-31T14:22:05+00:00") == "2026-03-31T14-22-05+00-00"

    def test_non_utc_offset_normalized(self) -> None:
        # +05:30 offset: 23:50 IST = 18:20 UTC
        result = _sanitize_timestamp("2026-03-31T23:50:00+05:30")
        assert result == "2026-03-31T18-20-00+00-00"

    def test_negative_offset_normalized(self) -> None:
        # -08:00 offset: 08:00 PST = 16:00 UTC
        result = _sanitize_timestamp("2026-03-31T08:00:00-08:00")
        assert result == "2026-03-31T16-00-00+00-00"

    def test_non_iso_passthrough(self) -> None:
        assert _sanitize_timestamp("2026-03-31") == "2026-03-31"
