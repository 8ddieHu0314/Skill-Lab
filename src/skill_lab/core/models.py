"""Core data models for the evaluation framework."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


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
    EXECUTION = "execution"  # Phase 3: Trace-based checks


class TriggerType(str, Enum):
    """Types of trigger tests based on OpenAI methodology."""

    EXPLICIT = "explicit"  # Skill named directly with $ prefix
    IMPLICIT = "implicit"  # Describes exact scenario without naming skill
    CONTEXTUAL = "contextual"  # Realistic noisy prompt with domain context
    NEGATIVE = "negative"  # Should NOT trigger (catches false positives)


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
    metadata: SkillMetadata | None
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
    details: dict[str, Any] | None = None
    location: str | None = None

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
    skill_name: str | None
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


# =============================================================================
# Phase 2: Trigger Testing Models
# =============================================================================


@dataclass(frozen=True)
class TraceEvent:
    """Normalized event from any runtime (Codex or Claude).

    Provides a common interface for analyzing traces regardless of the
    underlying runtime's native format.
    """

    type: str  # e.g., "item.started", "item.completed"
    item_type: str | None = None  # e.g., "command_execution", "skill_invocation"
    command: str | None = None  # The command that was run
    output: str | None = None  # Command output/result
    timestamp: str | None = None  # When it occurred
    raw: dict[str, Any] = field(default_factory=dict)  # Original event for debugging

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {"type": self.type}
        if self.item_type is not None:
            result["item_type"] = self.item_type
        if self.command is not None:
            result["command"] = self.command
        if self.output is not None:
            result["output"] = self.output
        if self.timestamp is not None:
            result["timestamp"] = self.timestamp
        return result


@dataclass(frozen=True)
class TriggerExpectation:
    """Expected outcomes for a trigger test."""

    skill_triggered: bool
    exit_code: int | None = None
    commands_include: tuple[str, ...] = field(default_factory=tuple)
    files_created: tuple[str, ...] = field(default_factory=tuple)
    no_loops: bool = False


@dataclass(frozen=True)
class TriggerTestCase:
    """A single trigger test case loaded from YAML.

    Supports both the full Given/When/Then DSL and simpler flat formats.
    """

    id: str
    name: str
    skill_name: str
    prompt: str
    trigger_type: TriggerType
    expected: TriggerExpectation
    runtime: str | None = None  # Override default runtime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "skill_name": self.skill_name,
            "prompt": self.prompt,
            "trigger_type": self.trigger_type.value,
            "expected": {
                "skill_triggered": self.expected.skill_triggered,
                "exit_code": self.expected.exit_code,
                "commands_include": list(self.expected.commands_include),
                "files_created": list(self.expected.files_created),
                "no_loops": self.expected.no_loops,
            },
            "runtime": self.runtime,
        }


@dataclass(frozen=True)
class TriggerResult:
    """Result of executing a single trigger test."""

    test_id: str
    test_name: str
    trigger_type: TriggerType
    passed: bool
    skill_triggered: bool
    expected_trigger: bool
    message: str
    trace_path: Path | None = None
    events_count: int = 0
    exit_code: int | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "trigger_type": self.trigger_type.value,
            "passed": self.passed,
            "skill_triggered": self.skill_triggered,
            "expected_trigger": self.expected_trigger,
            "message": self.message,
            "events_count": self.events_count,
        }
        if self.trace_path is not None:
            result["trace_path"] = str(self.trace_path)
        if self.exit_code is not None:
            result["exit_code"] = self.exit_code
        if self.details is not None:
            result["details"] = self.details
        return result


@dataclass
class TriggerReport:
    """Complete trigger test report for a skill."""

    skill_path: str
    skill_name: str
    timestamp: str
    duration_ms: float
    runtime: str
    tests_run: int
    tests_passed: int
    tests_failed: int
    overall_pass: bool
    pass_rate: float
    results: list[TriggerResult]
    summary_by_type: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "skill_path": self.skill_path,
            "skill_name": self.skill_name,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "runtime": self.runtime,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "overall_pass": self.overall_pass,
            "pass_rate": self.pass_rate,
            "results": [r.to_dict() for r in self.results],
            "summary_by_type": self.summary_by_type,
        }


# =============================================================================
# Phase 3: Trace Analysis Models
# =============================================================================


@dataclass(frozen=True)
class TraceCheckDefinition:
    """A trace check defined in YAML.

    Skill authors define these in tests/trace_checks.yaml to specify
    custom validations for execution traces.
    """

    id: str
    type: str  # command_presence, file_creation, event_sequence, loop_detection, efficiency
    description: str | None = None
    pattern: str | None = None  # for command_presence
    path: str | None = None  # for file_creation
    sequence: tuple[str, ...] = field(default_factory=tuple)  # for event_sequence
    max_retries: int = 3  # for loop_detection
    max_commands: int | None = None  # for efficiency


@dataclass(frozen=True)
class TraceCheckResult:
    """Result of a single trace check execution."""

    check_id: str
    check_type: str
    passed: bool
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "check_id": self.check_id,
            "check_type": self.check_type,
            "passed": self.passed,
            "message": self.message,
        }
        if self.details is not None:
            result["details"] = self.details
        return result


@dataclass
class TraceReport:
    """Complete trace evaluation report."""

    trace_path: str
    project_dir: str
    timestamp: str
    duration_ms: float
    checks_run: int
    checks_passed: int
    checks_failed: int
    overall_pass: bool
    pass_rate: float
    results: list[TraceCheckResult]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "trace_path": self.trace_path,
            "project_dir": self.project_dir,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "checks_run": self.checks_run,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "overall_pass": self.overall_pass,
            "pass_rate": self.pass_rate,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
        }
