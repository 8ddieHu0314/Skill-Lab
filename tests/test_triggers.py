"""Unit tests for trigger testing functionality."""

from pathlib import Path

import pytest

from skill_lab.core.models import TraceEvent, TriggerType
from skill_lab.triggers.test_loader import load_trigger_tests
from skill_lab.triggers.trace_analyzer import TraceAnalyzer


class TestTriggerTestLoader:
    """Tests for YAML test case loading."""

    def test_load_scenarios_yaml(self, fixtures_dir: Path) -> None:
        """Test loading Given/When/Then DSL format."""
        skill_path = fixtures_dir / "skills" / "creating-reports"
        test_cases, errors = load_trigger_tests(skill_path)

        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(test_cases) == 4

        # Check first test case
        explicit_test = next(t for t in test_cases if t.trigger_type == TriggerType.EXPLICIT)
        assert explicit_test.name == "Direct skill invocation"
        assert explicit_test.skill_name == "creating-reports"
        assert "$creating-reports" in explicit_test.prompt
        assert explicit_test.expected.skill_triggered is True

        # Check negative test
        negative_test = next(t for t in test_cases if t.trigger_type == TriggerType.NEGATIVE)
        assert negative_test.expected.skill_triggered is False

    def test_load_triggers_yaml(self, fixtures_dir: Path) -> None:
        """Test loading simple flat format."""
        skill_path = fixtures_dir / "skills" / "testing-features"
        test_cases, errors = load_trigger_tests(skill_path)

        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(test_cases) == 3

        # Check IDs are preserved
        ids = [tc.id for tc in test_cases]
        assert "explicit-1" in ids
        assert "implicit-1" in ids
        assert "negative-1" in ids

    def test_load_no_tests_directory(self, fixtures_dir: Path) -> None:
        """Test error handling when tests/ directory doesn't exist."""
        skill_path = fixtures_dir / "skills" / "invalid-skill"
        test_cases, errors = load_trigger_tests(skill_path)

        assert len(test_cases) == 0
        assert len(errors) >= 1
        assert "No tests/ directory found" in errors[0]

    def test_trigger_type_parsing(self, fixtures_dir: Path) -> None:
        """Test that all trigger types are correctly parsed."""
        skill_path = fixtures_dir / "skills" / "creating-reports"
        test_cases, _ = load_trigger_tests(skill_path)

        trigger_types = {tc.trigger_type for tc in test_cases}
        assert TriggerType.EXPLICIT in trigger_types
        assert TriggerType.IMPLICIT in trigger_types
        assert TriggerType.CONTEXTUAL in trigger_types
        assert TriggerType.NEGATIVE in trigger_types


class TestTraceAnalyzer:
    """Tests for trace analysis functionality."""

    @pytest.fixture
    def sample_events(self) -> list[TraceEvent]:
        """Create sample trace events for testing."""
        return [
            TraceEvent(
                type="item.started",
                item_type="skill_invocation",
                command="$my-skill run",
                raw={"type": "item.started", "item": {"type": "skill_invocation"}},
            ),
            TraceEvent(
                type="item.completed",
                item_type="command_execution",
                command="npm install",
                output="added 100 packages",
                raw={},
            ),
            TraceEvent(
                type="item.completed",
                item_type="command_execution",
                command="npm run build",
                output="Build successful",
                raw={},
            ),
            TraceEvent(
                type="item.completed",
                item_type="command_execution",
                command="npm install",  # Duplicate for loop detection
                output="added 0 packages",
                raw={},
            ),
        ]

    def test_skill_was_triggered(self, sample_events: list[TraceEvent]) -> None:
        """Test skill invocation detection."""
        analyzer = TraceAnalyzer(sample_events)

        assert analyzer.skill_was_triggered("my-skill") is True
        assert analyzer.skill_was_triggered("other-skill") is False

    def test_command_was_run(self, sample_events: list[TraceEvent]) -> None:
        """Test command presence detection."""
        analyzer = TraceAnalyzer(sample_events)

        assert analyzer.command_was_run("npm install") is True
        assert analyzer.command_was_run("npm run build") is True
        assert analyzer.command_was_run("npm test") is False

    def test_get_command_sequence(self, sample_events: list[TraceEvent]) -> None:
        """Test command sequence extraction."""
        analyzer = TraceAnalyzer(sample_events)
        commands = analyzer.get_command_sequence()

        assert len(commands) == 3
        assert commands[0] == "npm install"
        assert commands[1] == "npm run build"
        assert commands[2] == "npm install"

    def test_detect_loops(self, sample_events: list[TraceEvent]) -> None:
        """Test loop/thrashing detection."""
        analyzer = TraceAnalyzer(sample_events)

        # With max_repeats=3, should not detect loop (only 2 "npm install")
        assert analyzer.detect_loops(max_repeats=3) is False

        # With max_repeats=1, should detect loop
        assert analyzer.detect_loops(max_repeats=1) is True

    def test_count_events_by_type(self, sample_events: list[TraceEvent]) -> None:
        """Test event counting."""
        analyzer = TraceAnalyzer(sample_events)
        counts = analyzer.count_events_by_type()

        assert counts["item.started"] == 1
        assert counts["item.completed"] == 3

    def test_has_errors(self) -> None:
        """Test error detection."""
        events = [
            TraceEvent(type="item.completed", raw={}),
            TraceEvent(type="error", raw={"message": "Something failed"}),
        ]
        analyzer = TraceAnalyzer(events)

        assert analyzer.has_errors() is True
        errors = analyzer.get_error_messages()
        assert "Something failed" in errors

    def test_empty_trace(self) -> None:
        """Test handling of empty trace."""
        analyzer = TraceAnalyzer([])

        assert analyzer.skill_was_triggered("any-skill") is False
        assert analyzer.command_was_run("any-command") is False
        assert analyzer.get_command_sequence() == []
        assert analyzer.detect_loops() is False


class TestTriggerTestCaseSerialization:
    """Tests for data model serialization."""

    def test_trigger_test_case_to_dict(self, fixtures_dir: Path) -> None:
        """Test TriggerTestCase serialization."""
        skill_path = fixtures_dir / "skills" / "creating-reports"
        test_cases, _ = load_trigger_tests(skill_path)

        test_case = test_cases[0]
        result = test_case.to_dict()

        assert "id" in result
        assert "name" in result
        assert "skill_name" in result
        assert "prompt" in result
        assert "trigger_type" in result
        assert "expected" in result
        assert isinstance(result["expected"], dict)


class TestTriggerResult:
    """Tests for TriggerResult data model."""

    def test_trigger_result_to_dict(self) -> None:
        """Test TriggerResult serialization."""
        from skill_lab.core.models import TriggerResult

        result = TriggerResult(
            test_id="test-1",
            test_name="Test 1",
            trigger_type=TriggerType.EXPLICIT,
            passed=True,
            skill_triggered=True,
            expected_trigger=True,
            message="Test passed",
            events_count=5,
            exit_code=0,
        )

        result_dict = result.to_dict()

        assert result_dict["test_id"] == "test-1"
        assert result_dict["passed"] is True
        assert result_dict["trigger_type"] == "explicit"
        assert result_dict["events_count"] == 5


class TestTriggerReport:
    """Tests for TriggerReport data model."""

    def test_trigger_report_to_dict(self) -> None:
        """Test TriggerReport serialization."""
        from skill_lab.core.models import TriggerReport, TriggerResult

        result = TriggerResult(
            test_id="test-1",
            test_name="Test 1",
            trigger_type=TriggerType.EXPLICIT,
            passed=True,
            skill_triggered=True,
            expected_trigger=True,
            message="Test passed",
        )

        report = TriggerReport(
            skill_path="/path/to/skill",
            skill_name="my-skill",
            timestamp="2026-01-27T12:00:00Z",
            duration_ms=100.5,
            runtime="codex",
            tests_run=1,
            tests_passed=1,
            tests_failed=0,
            overall_pass=True,
            pass_rate=1.0,
            results=[result],
            summary_by_type={"explicit": {"total": 1, "passed": 1, "failed": 0}},
        )

        report_dict = report.to_dict()

        assert report_dict["skill_name"] == "my-skill"
        assert report_dict["overall_pass"] is True
        assert len(report_dict["results"]) == 1
        assert "explicit" in report_dict["summary_by_type"]
