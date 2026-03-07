"""Unit tests for skill_lab.parsers.trace_parser."""

from pathlib import Path

import pytest

from skill_lab.parsers.trace_parser import _parse_event, parse_trace_file


# ─── parse_trace_file ─────────────────────────────────────────────────────────


class TestParseTraceFileErrors:
    def test_raises_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="not found"):
            parse_trace_file(tmp_path / "nonexistent.jsonl")

    def test_file_not_found_message_includes_path(self, tmp_path: Path):
        target = tmp_path / "missing.jsonl"
        with pytest.raises(FileNotFoundError, match="missing.jsonl"):
            parse_trace_file(target)

    def test_invalid_json_raises_value_error(self, tmp_path: Path):
        p = tmp_path / "bad.jsonl"
        p.write_text("not json\n")
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_trace_file(p)

    def test_error_message_includes_line_number_1(self, tmp_path: Path):
        p = tmp_path / "trace.jsonl"
        p.write_text("not-json\n")
        with pytest.raises(ValueError, match="line 1"):
            parse_trace_file(p)

    def test_error_message_includes_correct_line_number(self, tmp_path: Path):
        p = tmp_path / "trace.jsonl"
        p.write_text('{"type": "ok"}\nnot-json\n')
        with pytest.raises(ValueError, match="line 2"):
            parse_trace_file(p)

    def test_error_on_third_line(self, tmp_path: Path):
        p = tmp_path / "trace.jsonl"
        p.write_text('{"type": "a"}\n{"type": "b"}\n{bad}\n')
        with pytest.raises(ValueError, match="line 3"):
            parse_trace_file(p)


class TestParseTraceFileBasicParsing:
    def test_empty_file_returns_empty_list(self, tmp_path: Path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        assert parse_trace_file(p) == []

    def test_blank_lines_skipped(self, tmp_path: Path):
        p = tmp_path / "trace.jsonl"
        p.write_text('\n\n{"type": "evt"}\n\n')
        events = parse_trace_file(p)
        assert len(events) == 1

    def test_whitespace_only_lines_skipped(self, tmp_path: Path):
        p = tmp_path / "trace.jsonl"
        p.write_text('{"type": "x"}\n   \n\t\n{"type": "y"}\n')
        events = parse_trace_file(p)
        assert len(events) == 2

    def test_parses_single_event(self, tmp_path: Path):
        p = tmp_path / "trace.jsonl"
        p.write_text('{"type": "item.started"}\n')
        events = parse_trace_file(p)
        assert len(events) == 1
        assert events[0].type == "item.started"

    def test_parses_multiple_events(self, tmp_path: Path):
        lines = ['{"type": "a"}', '{"type": "b"}', '{"type": "c"}']
        p = tmp_path / "trace.jsonl"
        p.write_text("\n".join(lines))
        events = parse_trace_file(p)
        assert len(events) == 3

    def test_event_types_in_order(self, tmp_path: Path):
        lines = ['{"type": "first"}', '{"type": "second"}', '{"type": "third"}']
        p = tmp_path / "trace.jsonl"
        p.write_text("\n".join(lines))
        events = parse_trace_file(p)
        assert events[0].type == "first"
        assert events[1].type == "second"
        assert events[2].type == "third"

    def test_returns_list_of_trace_events(self, tmp_path: Path):
        from skill_lab.core.models import TraceEvent

        p = tmp_path / "trace.jsonl"
        p.write_text('{"type": "x"}\n')
        events = parse_trace_file(p)
        assert all(isinstance(e, TraceEvent) for e in events)

    def test_parses_sample_trace_fixture(self, sample_trace_path: Path):
        events = parse_trace_file(sample_trace_path)
        assert len(events) > 0
        for event in events:
            assert event.type  # all events have a non-empty type

    def test_all_events_have_raw_field(self, tmp_path: Path):
        lines = ['{"type": "a", "key": 1}', '{"type": "b", "key": 2}']
        p = tmp_path / "trace.jsonl"
        p.write_text("\n".join(lines))
        events = parse_trace_file(p)
        assert events[0].raw == {"type": "a", "key": 1}
        assert events[1].raw == {"type": "b", "key": 2}


# ─── _parse_event: type field ─────────────────────────────────────────────────


class TestParseEventType:
    def test_type_extracted(self):
        event = _parse_event({"type": "item.completed"})
        assert event.type == "item.completed"

    def test_missing_type_defaults_to_unknown(self):
        event = _parse_event({})
        assert event.type == "unknown"

    def test_empty_string_type(self):
        event = _parse_event({"type": ""})
        assert event.type == ""


# ─── _parse_event: raw field ──────────────────────────────────────────────────


class TestParseEventRaw:
    def test_raw_is_original_dict(self):
        data = {"type": "x", "extra": 42}
        event = _parse_event(data)
        assert event.raw == data

    def test_raw_is_exact_same_object(self):
        data = {"type": "x"}
        event = _parse_event(data)
        assert event.raw is data

    def test_raw_with_nested_structure(self):
        data = {"type": "x", "item": {"type": "function_call", "name": "tool"}}
        event = _parse_event(data)
        assert event.raw["item"]["name"] == "tool"


# ─── _parse_event: Codex function_call format ─────────────────────────────────


class TestParseEventCodexFunctionCall:
    def test_function_call_sets_command_to_name(self):
        data = {
            "type": "item.completed",
            "item": {"type": "function_call", "name": "bash", "arguments": ""},
        }
        event = _parse_event(data)
        assert event.command == "bash"

    def test_function_call_appends_nonempty_args(self):
        data = {
            "type": "item.completed",
            "item": {
                "type": "function_call",
                "name": "bash",
                "arguments": '{"command": "ls -la"}',
            },
        }
        event = _parse_event(data)
        assert event.command is not None
        assert "bash" in event.command
        assert '{"command": "ls -la"}' in event.command

    def test_function_call_empty_args_not_appended(self):
        data = {
            "type": "x",
            "item": {"type": "function_call", "name": "mytool", "arguments": ""},
        }
        event = _parse_event(data)
        assert event.command == "mytool"

    def test_function_call_sets_item_type(self):
        data = {"type": "x", "item": {"type": "function_call", "name": "t", "arguments": ""}}
        event = _parse_event(data)
        assert event.item_type == "function_call"

    def test_function_call_output_is_none(self):
        data = {"type": "x", "item": {"type": "function_call", "name": "t", "arguments": ""}}
        event = _parse_event(data)
        assert event.output is None

    def test_function_call_missing_name_gives_empty_command(self):
        data = {"type": "x", "item": {"type": "function_call", "arguments": ""}}
        event = _parse_event(data)
        assert event.command == ""


# ─── _parse_event: Codex function_call_output format ─────────────────────────


class TestParseEventFunctionCallOutput:
    def test_output_is_extracted(self):
        data = {
            "type": "item.completed",
            "item": {"type": "function_call_output", "output": "the result"},
        }
        event = _parse_event(data)
        assert event.output == "the result"

    def test_item_type_is_set(self):
        data = {"type": "x", "item": {"type": "function_call_output", "output": "x"}}
        event = _parse_event(data)
        assert event.item_type == "function_call_output"

    def test_command_is_none(self):
        data = {"type": "x", "item": {"type": "function_call_output", "output": "x"}}
        event = _parse_event(data)
        assert event.command is None

    def test_missing_output_key_gives_empty_string(self):
        # item.get("output", "") returns "" when key is absent
        data = {"type": "x", "item": {"type": "function_call_output"}}
        event = _parse_event(data)
        assert event.output == ""


# ─── _parse_event: Codex command_execution item type ─────────────────────────


class TestParseEventCodexCommandExecution:
    def test_command_from_top_level_key(self):
        data = {
            "type": "item.completed",
            "item": {"type": "command_execution"},
            "command": "npm install",
            "output": "packages installed",
        }
        event = _parse_event(data)
        assert event.command == "npm install"

    def test_output_from_top_level_key(self):
        data = {
            "type": "item.completed",
            "item": {"type": "command_execution"},
            "command": "npm install",
            "output": "packages installed",
        }
        event = _parse_event(data)
        assert event.output == "packages installed"

    def test_item_type_is_command_execution(self):
        data = {
            "type": "x",
            "item": {"type": "command_execution"},
            "command": "ls",
        }
        event = _parse_event(data)
        assert event.item_type == "command_execution"


# ─── _parse_event: direct command format (no item key) ───────────────────────


class TestParseEventDirectCommand:
    def test_direct_command_extracted(self):
        data = {"type": "cmd", "command": "git status", "output": "nothing to commit"}
        event = _parse_event(data)
        assert event.command == "git status"

    def test_direct_command_output_extracted(self):
        data = {"type": "cmd", "command": "git status", "output": "nothing to commit"}
        event = _parse_event(data)
        assert event.output == "nothing to commit"

    def test_direct_command_sets_item_type(self):
        data = {"type": "cmd", "command": "ls"}
        event = _parse_event(data)
        assert event.item_type == "command_execution"

    def test_direct_command_missing_output_gives_none(self):
        data = {"type": "cmd", "command": "pwd"}
        event = _parse_event(data)
        assert event.output is None


# ─── _parse_event: simplified function_call (top-level type == "function_call") ─


class TestParseEventSimplifiedFunctionCall:
    def test_command_includes_name(self):
        data = {"type": "function_call", "name": "bash", "arguments": "ls -la"}
        event = _parse_event(data)
        assert event.command is not None
        assert "bash" in event.command

    def test_item_type_is_command_execution(self):
        data = {"type": "function_call", "name": "tool", "arguments": ""}
        event = _parse_event(data)
        assert event.item_type == "command_execution"

    def test_args_appended_when_nonempty(self):
        data = {"type": "function_call", "name": "tool", "arguments": "arg1 arg2"}
        event = _parse_event(data)
        assert "arg1 arg2" in event.command  # type: ignore[operator]

    def test_empty_args_not_appended(self):
        data = {"type": "function_call", "name": "tool", "arguments": ""}
        event = _parse_event(data)
        assert event.command == "tool"


# ─── _parse_event: timestamp extraction ──────────────────────────────────────


class TestParseEventTimestamp:
    def test_timestamp_from_timestamp_field(self):
        data = {"type": "x", "timestamp": "2024-01-01T00:00:00Z"}
        event = _parse_event(data)
        assert event.timestamp == "2024-01-01T00:00:00Z"

    def test_timestamp_from_time_field(self):
        data = {"type": "x", "time": "2024-06-15T12:30:00Z"}
        event = _parse_event(data)
        assert event.timestamp == "2024-06-15T12:30:00Z"

    def test_no_timestamp_field_gives_none(self):
        event = _parse_event({"type": "x"})
        assert event.timestamp is None

    def test_timestamp_takes_precedence_over_time(self):
        data = {"type": "x", "timestamp": "ts-value", "time": "time-value"}
        event = _parse_event(data)
        # data.get("timestamp") is non-falsy → used over "time"
        assert event.timestamp == "ts-value"

    def test_empty_timestamp_falls_back_to_time(self):
        # An empty string is falsy → falls through to "time" via `or`
        data = {"type": "x", "timestamp": "", "time": "time-value"}
        event = _parse_event(data)
        assert event.timestamp == "time-value"


# ─── _parse_event: unknown item types ────────────────────────────────────────


class TestParseEventUnknownItemType:
    def test_unknown_item_type_command_is_none(self):
        data = {"type": "x", "item": {"type": "something_unknown"}}
        event = _parse_event(data)
        assert event.command is None

    def test_unknown_item_type_output_is_none(self):
        data = {"type": "x", "item": {"type": "something_unknown"}}
        event = _parse_event(data)
        assert event.output is None

    def test_unknown_item_type_item_type_is_set(self):
        data = {"type": "x", "item": {"type": "something_unknown"}}
        event = _parse_event(data)
        assert event.item_type == "something_unknown"

    def test_item_with_no_type_key(self):
        data = {"type": "x", "item": {}}
        event = _parse_event(data)
        # item_type defaults to None since item has no "type"
        assert event.item_type is None


# ─── Integration: parse real fixture traces ───────────────────────────────────


class TestParseRealTraces:
    def test_sample_trace_all_events_have_type(self, sample_trace_path: Path):
        events = parse_trace_file(sample_trace_path)
        for event in events:
            assert isinstance(event.type, str)

    def test_sample_trace_events_have_raw(self, sample_trace_path: Path):
        events = parse_trace_file(sample_trace_path)
        for event in events:
            assert isinstance(event.raw, dict)

    def test_creating_reports_scenario_trace_is_not_compact_jsonl(self, fixtures_dir: Path):
        """The scenario fixture uses pretty-printed multi-line JSON, not compact JSONL.
        parse_trace_file reads line-by-line and will raise ValueError on it — that is
        expected behaviour; this test documents that constraint."""
        trace = fixtures_dir / "skills" / "creating-reports" / ".skill-lab" / "traces" / "scenario-1.jsonl"
        if not trace.exists():
            pytest.skip("scenario-1.jsonl fixture not present")
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_trace_file(trace)

    def test_inline_jsonl_multiple_formats(self, tmp_path: Path):
        """End-to-end: a file mixing various event formats is parsed correctly."""
        lines = [
            '{"type": "system", "subtype": "init"}',
            '{"type": "item.completed", "item": {"type": "function_call", "name": "bash", "arguments": "ls"}}',
            '{"type": "item.completed", "item": {"type": "function_call_output", "output": "file.txt"}}',
            '{"type": "cmd", "command": "git status"}',
        ]
        p = tmp_path / "mixed.jsonl"
        p.write_text("\n".join(lines))
        events = parse_trace_file(p)
        assert len(events) == 4
        assert events[0].type == "system"
        assert events[1].command is not None and "bash" in events[1].command
        assert events[2].output == "file.txt"
        assert events[3].command == "git status"
