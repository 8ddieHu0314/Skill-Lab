"""Core components for the evaluation framework."""

from skill_lab.core.exceptions import (
    CheckExecutionError,
    ConfigurationError,
    ParseError,
    SkillLabError,
    TraceParseError,
    ValidationError,
)
from skill_lab.core.models import (
    CheckResult,
    EvalDimension,
    EvaluationReport,
    Severity,
    Skill,
    SkillMetadata,
)
from skill_lab.core.registry import CheckRegistry, registry
from skill_lab.core.scoring import calculate_score

__all__ = [
    # Exceptions
    "CheckExecutionError",
    "ConfigurationError",
    "ParseError",
    "SkillLabError",
    "TraceParseError",
    "ValidationError",
    # Models
    "CheckResult",
    "CheckRegistry",
    "EvalDimension",
    "EvaluationReport",
    "Severity",
    "Skill",
    "SkillMetadata",
    # Functions
    "calculate_score",
    "registry",
]
