"""Tests for trace check handlers."""

from pathlib import Path

import pytest

from skill_lab.core.models import TraceCheckDefinition, TraceEvent
from skill_lab.tracechecks.handlers import (
    CommandPresenceHandler,
    EfficiencyHandler,
    EventSequenceHandler,
    LoopDetectionHandler,
)
from skill_lab.triggers.trace_analyzer import TraceAnalyzer


@pytest.fixture
def sample_events() -> list[TraceEvent]:
    """Create sample trace events for testing."""
    return [
        TraceEvent(type="item.completed", item_type="command_execution", command="npm init -y"),
        TraceEvent(type="item.completed", item_type="command_execution", command="npm install express"),
        TraceEvent(type="item.completed", item_type="command_execution", command="npm run build"),
        TraceEvent(type="item.completed", item_type="command_execution", command="npm test"),
    ]


@pytest.fixture
def analyzer(sample_events: list[TraceEvent]) -> TraceAnalyzer:
    """Create a TraceAnalyzer with sample events."""
    return TraceAnalyzer(sample_events)


class TestCommandPresenceHandler:
    """Tests for CommandPresenceHandler."""

    def test_command_found(self, analyzer: TraceAnalyzer, tmp_path: Path):
        check = TraceCheckDefinition(id="test", type="command_presence", pattern="npm install")
        handler = CommandPresenceHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert result.passed
        assert "npm install" in result.message

    def test_command_not_found(self, analyzer: TraceAnalyzer, tmp_path: Path):
        check = TraceCheckDefinition(id="test", type="command_presence", pattern="yarn install")
        handler = CommandPresenceHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert not result.passed
        assert "yarn install" in result.message

    def test_missing_pattern(self, analyzer: TraceAnalyzer, tmp_path: Path):
        check = TraceCheckDefinition(id="test", type="command_presence")
        handler = CommandPresenceHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert not result.passed
        assert "Missing required 'pattern' field" in result.message


class TestEventSequenceHandler:
    """Tests for EventSequenceHandler."""

    def test_sequence_found(self, analyzer: TraceAnalyzer, tmp_path: Path):
        check = TraceCheckDefinition(
            id="test",
            type="event_sequence",
            sequence=("npm init", "npm install", "npm run build"),
        )
        handler = EventSequenceHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert result.passed
        assert "3 commands found" in result.message

    def test_sequence_partial(self, analyzer: TraceAnalyzer, tmp_path: Path):
        check = TraceCheckDefinition(
            id="test",
            type="event_sequence",
            sequence=("npm init", "npm install", "npm deploy"),  # deploy not present
        )
        handler = EventSequenceHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert not result.passed
        assert "npm deploy" in result.message

    def test_sequence_out_of_order(self, tmp_path: Path):
        events = [
            TraceEvent(type="item.completed", item_type="command_execution", command="npm run build"),
            TraceEvent(type="item.completed", item_type="command_execution", command="npm init"),
        ]
        analyzer = TraceAnalyzer(events)
        check = TraceCheckDefinition(
            id="test",
            type="event_sequence",
            sequence=("npm init", "npm run build"),
        )
        handler = EventSequenceHandler()

        # The sequence should fail because init comes after build
        result = handler.run(check, analyzer, tmp_path)

        # First pattern "npm init" matches at index 1, then "npm run build"
        # can't be found after index 1
        assert not result.passed

    def test_missing_sequence(self, analyzer: TraceAnalyzer, tmp_path: Path):
        check = TraceCheckDefinition(id="test", type="event_sequence")
        handler = EventSequenceHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert not result.passed
        assert "Missing required 'sequence' field" in result.message


class TestLoopDetectionHandler:
    """Tests for LoopDetectionHandler."""

    def test_no_loops(self, analyzer: TraceAnalyzer, tmp_path: Path):
        check = TraceCheckDefinition(id="test", type="loop_detection", max_retries=3)
        handler = LoopDetectionHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert result.passed
        assert "No command repeated" in result.message

    def test_loop_detected(self, tmp_path: Path):
        events = [
            TraceEvent(type="item.completed", item_type="command_execution", command="npm install"),
            TraceEvent(type="item.completed", item_type="command_execution", command="npm install"),
            TraceEvent(type="item.completed", item_type="command_execution", command="npm install"),
            TraceEvent(type="item.completed", item_type="command_execution", command="npm install"),
        ]
        analyzer = TraceAnalyzer(events)
        check = TraceCheckDefinition(id="test", type="loop_detection", max_retries=3)
        handler = LoopDetectionHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert not result.passed
        assert "4 times" in result.message


class TestEfficiencyHandler:
    """Tests for EfficiencyHandler."""

    def test_under_limit(self, analyzer: TraceAnalyzer, tmp_path: Path):
        check = TraceCheckDefinition(id="test", type="efficiency", max_commands=10)
        handler = EfficiencyHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert result.passed
        assert "4 commands" in result.message

    def test_over_limit(self, analyzer: TraceAnalyzer, tmp_path: Path):
        check = TraceCheckDefinition(id="test", type="efficiency", max_commands=2)
        handler = EfficiencyHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert not result.passed
        assert "exceeding limit" in result.message

    def test_missing_max_commands(self, analyzer: TraceAnalyzer, tmp_path: Path):
        check = TraceCheckDefinition(id="test", type="efficiency")
        handler = EfficiencyHandler()

        result = handler.run(check, analyzer, tmp_path)

        assert not result.passed
        assert "Missing required 'max_commands' field" in result.message
