"""Evaluation history persistence (.sklab/evals/).

Stores full evaluation results (static checks + optional LLM judge) as
timestamped JSON files. The optimizer reads the latest file to build its
prompt — this is the bridge between `sklab evaluate` and `sklab optimize`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skill_lab.core.constants import EVALS_DIR
from skill_lab.core.models import (
    CheckResult,
    EvalDimension,
    EvaluationReport,
    JudgeCriterion,
    JudgeResult,
    Severity,
)

logger = logging.getLogger(__name__)

MAX_EVAL_FILES = 20
EVAL_SCHEMA_VERSION = "2.0"


@dataclass(frozen=True)
class EvalRecord:
    """A single persisted evaluation record."""

    schema_version: str
    report: EvaluationReport
    judge: JudgeResult | None
    judge_model: str | None
    judge_usage: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            **self.report.to_dict(),
        }

        if self.judge is not None:
            judge_data = self.judge.to_dict()
            if self.judge_model is not None:
                judge_data["model"] = self.judge_model
            if self.judge_usage is not None:
                judge_data["usage"] = self.judge_usage
            data["judge"] = judge_data
        else:
            data["judge"] = None

        return data


def save_eval(
    skill_path: Path,
    report: EvaluationReport,
    *,
    judge_result: JudgeResult | None = None,
    judge_model: str | None = None,
    judge_usage: dict[str, Any] | None = None,
) -> Path:
    """Persist full evaluation results to .sklab/evals/{timestamp}.json.

    Creates the evals directory if needed. Prunes oldest files beyond
    MAX_EVAL_FILES after writing.

    Returns:
        Path to the written file.
    """
    evals_dir = skill_path / EVALS_DIR
    evals_dir.mkdir(parents=True, exist_ok=True)

    record = EvalRecord(
        schema_version=EVAL_SCHEMA_VERSION,
        report=report,
        judge=judge_result,
        judge_model=judge_model,
        judge_usage=judge_usage,
    )

    filename = _sanitize_timestamp(report.timestamp) + ".json"
    file_path = evals_dir / filename
    file_path.write_text(
        json.dumps(record.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )

    _prune_old_evals(evals_dir)
    return file_path


def load_latest_eval(skill_path: Path) -> EvalRecord | None:
    """Load the most recent eval from .sklab/evals/.

    Returns None if no eval files exist or the directory is missing.
    """
    evals_dir = skill_path / EVALS_DIR
    if not evals_dir.is_dir():
        return None

    files = sorted(evals_dir.glob("*.json"))
    if not files:
        return None

    return load_eval(files[-1])


def load_eval(path: Path) -> EvalRecord:
    """Parse a single eval JSON file into an EvalRecord.

    Raises:
        ValueError: If the file cannot be parsed.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"Cannot read eval file {path}: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Invalid eval file {path}: expected JSON object")

    return _rebuild_record(data)


def _prune_old_evals(evals_dir: Path, max_files: int = MAX_EVAL_FILES) -> None:
    """Remove oldest eval files if count exceeds max_files."""
    files = sorted(evals_dir.glob("*.json"))
    excess = len(files) - max_files
    if excess <= 0:
        return
    for f in files[:excess]:
        try:
            f.unlink()
        except OSError:
            logger.warning("Failed to prune eval file: %s", f)


def _sanitize_timestamp(ts: str) -> str:
    """Replace colons with hyphens for cross-platform filename safety."""
    return ts.replace(":", "-")


# ---------------------------------------------------------------------------
# Deserialization helpers
# ---------------------------------------------------------------------------


def _rebuild_record(data: dict[str, Any]) -> EvalRecord:
    """Reconstruct an EvalRecord from a parsed JSON dict."""
    report = _rebuild_report(data)
    judge: JudgeResult | None = None
    judge_model: str | None = None
    judge_usage: dict[str, Any] | None = None

    judge_data = data.get("judge")
    if isinstance(judge_data, dict):
        judge = _rebuild_judge(judge_data)
        judge_model = judge_data.get("model")
        usage_raw = judge_data.get("usage")
        if isinstance(usage_raw, dict):
            judge_usage = usage_raw

    return EvalRecord(
        schema_version=data.get("schema_version", "2.0"),
        report=report,
        judge=judge,
        judge_model=judge_model,
        judge_usage=judge_usage,
    )


def _rebuild_report(data: dict[str, Any]) -> EvaluationReport:
    """Reconstruct an EvaluationReport from a dict."""
    results = [_rebuild_check_result(r) for r in data.get("results", [])]
    return EvaluationReport(
        skill_path=data.get("skill_path", ""),
        skill_name=data.get("skill_name"),
        timestamp=data.get("timestamp", ""),
        duration_ms=float(data.get("duration_ms", 0)),
        quality_score=float(data.get("quality_score", 0)),
        overall_pass=bool(data.get("overall_pass", False)),
        checks_run=int(data.get("checks_run", 0)),
        checks_passed=int(data.get("checks_passed", 0)),
        checks_failed=int(data.get("checks_failed", 0)),
        results=results,
        summary=data.get("summary", {}),
    )


def _rebuild_check_result(data: dict[str, Any]) -> CheckResult:
    """Reconstruct a CheckResult from a dict."""
    return CheckResult(
        check_id=data.get("check_id", ""),
        check_name=data.get("check_name", ""),
        passed=bool(data.get("passed", False)),
        severity=Severity(data.get("severity", "low")),
        dimension=EvalDimension(data.get("dimension", "content")),
        message=data.get("message", ""),
        details=data.get("details"),
        location=data.get("location"),
        fix=data.get("fix"),
    )


def _rebuild_judge(data: dict[str, Any]) -> JudgeResult:
    """Reconstruct a JudgeResult from a dict."""
    criteria = tuple(
        JudgeCriterion(
            id=c.get("id", ""),
            name=c.get("name", ""),
            axis=c.get("axis", ""),
            score=int(c.get("score", 0)),
            reasoning=c.get("reasoning", ""),
        )
        for c in data.get("criteria", [])
    )
    return JudgeResult(
        criteria=criteria,
        activation_score=float(data.get("activation_score", 0)),
        instruction_score=float(data.get("instruction_score", 0)),
        judge_score=float(data.get("judge_score", 0)),
        verdict=data.get("verdict", ""),
        suggestions=tuple(data.get("suggestions", [])),
    )
