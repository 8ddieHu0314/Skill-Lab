"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest

from skill_lab.evaluators.static_evaluator import StaticEvaluator
from skill_lab.evaluators.trace_evaluator import TraceEvaluator


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
