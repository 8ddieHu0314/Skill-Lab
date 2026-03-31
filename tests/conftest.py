"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest

from skill_lab.core.eval_history import EvalRecord
from skill_lab.core.models import (
    CheckResult,
    EvalDimension,
    EvaluationReport,
    JudgeCriterion,
    JudgeResult,
    Severity,
)
from skill_lab.evaluators.static_evaluator import StaticEvaluator
from skill_lab.evaluators.trace_evaluator import TraceEvaluator

# ---------------------------------------------------------------------------
# Shared test factory functions for evaluation data
# ---------------------------------------------------------------------------


def make_report(
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


def make_judge(score: float = 68.8) -> JudgeResult:
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


def make_eval_record(
    score: float = 65.0,
    judge: JudgeResult | None = None,
) -> EvalRecord:
    """Build a minimal EvalRecord for testing."""
    report = make_report(score=score)
    return EvalRecord(
        schema_version="2.0",
        report=report,
        judge=judge,
        judge_model="claude-haiku-4-5-20251001" if judge else None,
        judge_usage=None,
    )


@pytest.fixture
def fixtures_dir() -> Path:
    """Get the path to the fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def skills_dir(fixtures_dir: Path) -> Path:
    """Get the path to the skills fixtures directory."""
    return fixtures_dir / "skills"


@pytest.fixture
def valid_skill_path(skills_dir: Path) -> Path:
    """Get the path to a valid skill fixture."""
    return skills_dir / "creating-reports"


@pytest.fixture
def invalid_skill_path(skills_dir: Path) -> Path:
    """Get the path to an invalid skill fixture."""
    return skills_dir / "invalid-skill"


@pytest.fixture
def minimal_skill_path(skills_dir: Path) -> Path:
    """Get the path to a minimal valid skill fixture."""
    return skills_dir / "testing-features"


@pytest.fixture
def evaluator() -> StaticEvaluator:
    """Get a StaticEvaluator instance."""
    return StaticEvaluator()


@pytest.fixture
def traces_dir(fixtures_dir: Path) -> Path:
    """Get the path to the traces fixtures directory."""
    return fixtures_dir / "traces"


@pytest.fixture
def sample_trace_path(traces_dir: Path) -> Path:
    """Get the path to the sample trace file."""
    return traces_dir / "sample_trace.jsonl"


@pytest.fixture
def trace_evaluator() -> TraceEvaluator:
    """Get a TraceEvaluator instance."""
    return TraceEvaluator()
