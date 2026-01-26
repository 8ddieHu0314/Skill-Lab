"""Core data models for the evaluation framework."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class Severity(str, Enum):
    """Severity levels for check results."""

    ERROR = "error"  # Must fix
    WARNING = "warning"  # Should fix
    INFO = "info"  # Suggestion


class EvalDimension(str, Enum):
    """Evaluation dimensions for categorizing checks."""

    STRUCTURE = "structure"
    NAMING = "naming"
    DESCRIPTION = "description"
    CONTENT = "content"


@dataclass(frozen=True)
class SkillMetadata:
    """Metadata extracted from SKILL.md frontmatter."""

    name: str
    description: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Skill:
    """Parsed skill representation."""

    path: Path
    metadata: Optional[SkillMetadata]
    body: str
    has_scripts: bool
    has_references: bool
    has_assets: bool
    parse_errors: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CheckResult:
    """Result of a single check execution."""

    check_id: str
    check_name: str
    passed: bool
    severity: Severity
    dimension: EvalDimension
    message: str
    details: Optional[dict[str, Any]] = None
    location: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "passed": self.passed,
            "severity": self.severity.value,
            "dimension": self.dimension.value,
            "message": self.message,
        }
        if self.details is not None:
            result["details"] = self.details
        if self.location is not None:
            result["location"] = self.location
        return result


@dataclass
class EvaluationReport:
    """Complete evaluation report for a skill."""

    skill_path: str
    skill_name: Optional[str]
    timestamp: str
    duration_ms: float
    quality_score: float
    overall_pass: bool
    checks_run: int
    checks_passed: int
    checks_failed: int
    results: list[CheckResult]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "skill_path": self.skill_path,
            "skill_name": self.skill_name,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "quality_score": self.quality_score,
            "overall_pass": self.overall_pass,
            "checks_run": self.checks_run,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
        }
