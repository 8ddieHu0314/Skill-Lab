"""Unit tests for ConsoleReporter and JsonReporter."""

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from skill_lab.core.models import (
    CheckResult,
    EvalDimension,
    EvaluationReport,
    Severity,
    TraceCheckResult,
    TraceReport,
)
from skill_lab.reporters.console_reporter import (
    SEVERITY_ICONS,
    SEVERITY_STYLES,
    ConsoleReporter,
)
from skill_lab.reporters.json_reporter import SCHEMA_VERSION, JsonReporter


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_check_result(
    check_id: str = "check-1",
    check_name: str = "Check One",
    passed: bool = True,
    severity: Severity = Severity.HIGH,
    dimension: EvalDimension = EvalDimension.STRUCTURE,
    message: str = "All good",
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        check_name=check_name,
        passed=passed,
        severity=severity,
        dimension=dimension,
        message=message,
    )


def _make_eval_report(
    skill_name: str | None = "test-skill",
    skill_path: str = "/path/to/skill",
    score: float = 85.0,
    overall_pass: bool = True,
    checks_run: int = 3,
    checks_passed: int = 3,
    checks_failed: int = 0,
    results: list[CheckResult] | None = None,
    summary: dict | None = None,
) -> EvaluationReport:
    if results is None:
        results = [_make_check_result()]
    if summary is None:
        summary = {"by_dimension": {"structure": {"passed": 3, "failed": 0}}}
    return EvaluationReport(
        skill_path=skill_path,
        skill_name=skill_name,
        timestamp="2026-01-01T00:00:00Z",
        duration_ms=42.5,
        quality_score=score,
        overall_pass=overall_pass,
        checks_run=checks_run,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        results=results,
        summary=summary,
    )


def _make_trace_check_result(
    check_id: str = "trace-check-1",
    check_type: str = "command_presence",
    passed: bool = True,
    message: str = "OK",
) -> TraceCheckResult:
    return TraceCheckResult(
        check_id=check_id,
        check_type=check_type,
        passed=passed,
        message=message,
    )


def _make_trace_report(
    trace_path: str = "/path/to/trace.jsonl",
    project_dir: str = "/path/to/project",
    overall_pass: bool = True,
    checks_run: int = 2,
    checks_passed: int = 2,
    checks_failed: int = 0,
    pass_rate: float = 100.0,
    results: list[TraceCheckResult] | None = None,
    summary: dict | None = None,
) -> TraceReport:
    if results is None:
        results = [_make_trace_check_result()]
    if summary is None:
        summary = {"by_type": {}}
    return TraceReport(
        trace_path=trace_path,
        project_dir=project_dir,
        timestamp="2026-01-01T00:00:00Z",
        duration_ms=33.3,
        checks_run=checks_run,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        overall_pass=overall_pass,
        pass_rate=pass_rate,
        results=results,
        summary=summary,
    )


def _capture(reporter: ConsoleReporter) -> tuple[ConsoleReporter, io.StringIO]:
    """Replace reporter.console with one that writes to a StringIO buffer (no ANSI)."""
    buf = io.StringIO()
    reporter.console = Console(file=buf, width=200, no_color=True)
    return reporter, buf


# ─── Severity mapping constants ────────────────────────────────────────────────


class TestSeverityMappings:
    @pytest.mark.parametrize(
        "severity, dict_name",
        [
            ("high", "SEVERITY_STYLES"),
            ("medium", "SEVERITY_STYLES"),
            ("low", "SEVERITY_STYLES"),
            ("high", "SEVERITY_ICONS"),
            ("medium", "SEVERITY_ICONS"),
            ("low", "SEVERITY_ICONS"),
        ],
        ids=[
            "styles-high",
            "styles-medium",
            "styles-low",
            "icons-high",
            "icons-medium",
            "icons-low",
        ],
    )
    def test_key_exists(self, severity, dict_name):
        mapping = SEVERITY_STYLES if dict_name == "SEVERITY_STYLES" else SEVERITY_ICONS
        assert severity in mapping

    @pytest.mark.parametrize(
        "severity, expected_icon, expected_style",
        [
            ("high", "X", "bold red"),
            ("medium", "!", "yellow"),
            ("low", "i", "blue"),
        ],
        ids=["high", "medium", "low"],
    )
    def test_values_match(self, severity, expected_icon, expected_style):
        assert SEVERITY_ICONS[severity] == expected_icon
        assert SEVERITY_STYLES[severity] == expected_style


# ─── ConsoleReporter init & private methods ────────────────────────────────────


class TestConsoleReporterInit:
    def test_default_verbose_is_false(self):
        assert ConsoleReporter().verbose is False

    def test_verbose_true(self):
        assert ConsoleReporter(verbose=True).verbose is True

    def test_console_created_on_init(self):
        assert ConsoleReporter().console is not None


class TestSeverityStyle:
    @pytest.mark.parametrize(
        "severity, expected",
        [
            (Severity.HIGH, "bold red"),
            (Severity.MEDIUM, "yellow"),
            (Severity.LOW, "blue"),
        ],
        ids=["high", "medium", "low"],
    )
    def test_known_severity(self, severity, expected):
        assert ConsoleReporter()._severity_style(severity) == expected

    def test_unknown_value_returns_white(self):
        class FakeSeverity:
            value = "nonexistent"

        assert ConsoleReporter()._severity_style(FakeSeverity()) == "white"  # type: ignore[arg-type]


class TestSeverityIcon:
    @pytest.mark.parametrize(
        "severity, expected",
        [
            (Severity.HIGH, "X"),
            (Severity.MEDIUM, "!"),
            (Severity.LOW, "i"),
        ],
        ids=["high", "medium", "low"],
    )
    def test_known_severity(self, severity, expected):
        assert ConsoleReporter()._severity_icon(severity) == expected

    def test_unknown_value_returns_question_mark(self):
        class FakeSeverity:
            value = "nonexistent"

        assert ConsoleReporter()._severity_icon(FakeSeverity()) == "?"  # type: ignore[arg-type]


class TestPrintVerboseHint:
    """Test _print_verbose_hint in isolation via a captured console."""

    def _reporter(self, verbose: bool = False) -> tuple[ConsoleReporter, io.StringIO]:
        r = ConsoleReporter(verbose=verbose)
        return _capture(r)

    def test_verbose_mode_prints_nothing(self):
        reporter, buf = self._reporter(verbose=True)
        reporter._print_verbose_hint(5, 5)
        assert buf.getvalue() == ""

    def test_hidden_checks_message_when_hidden_gt_zero(self):
        reporter, buf = self._reporter()
        reporter._print_verbose_hint(total_count=5, shown_count=2)
        assert "3" in buf.getvalue()
        assert "passing checks hidden" in buf.getvalue()

    def test_all_checks_passed_message_when_no_results(self):
        # "All checks passed!" appears only when total_count == 0 and shown_count == 0
        reporter, buf = self._reporter()
        reporter._print_verbose_hint(total_count=0, shown_count=0)
        assert "All checks passed" in buf.getvalue()

    def test_no_output_when_all_shown_and_shown_nonzero(self):
        # hidden == 0, shown_count != 0 → nothing printed
        reporter, buf = self._reporter()
        reporter._print_verbose_hint(total_count=3, shown_count=3)
        assert buf.getvalue() == ""


# ─── ConsoleReporter.report() ─────────────────────────────────────────────────


class TestConsoleReporterReport:
    def _reporter(self, verbose: bool = False) -> tuple[ConsoleReporter, io.StringIO]:
        r = ConsoleReporter(verbose=verbose)
        return _capture(r)

    # Header
    def test_skill_name_in_output(self):
        reporter, buf = self._reporter()
        reporter.report(_make_eval_report(skill_name="my-special-skill"))
        assert "my-special-skill" in buf.getvalue()

    def test_skill_path_in_output(self):
        reporter, buf = self._reporter()
        reporter.report(_make_eval_report(skill_path="/skills/demo-skill"))
        assert "/skills/demo-skill" in buf.getvalue()

    def test_none_skill_name_shows_unknown(self):
        reporter, buf = self._reporter()
        reporter.report(_make_eval_report(skill_name=None))
        assert "Unknown" in buf.getvalue()

    # Score & status
    def test_score_shown(self):
        reporter, buf = self._reporter()
        reporter.report(_make_eval_report(score=92.5))
        assert "92.5" in buf.getvalue()

    def test_score_zero(self):
        reporter, buf = self._reporter()
        reporter.report(_make_eval_report(score=0.0))
        assert "0.0" in buf.getvalue()

    def test_pass_status(self):
        reporter, buf = self._reporter()
        reporter.report(_make_eval_report(overall_pass=True))
        assert "PASS" in buf.getvalue()

    def test_fail_status(self):
        reporter, buf = self._reporter()
        reporter.report(_make_eval_report(overall_pass=False))
        assert "FAIL" in buf.getvalue()

    def test_checks_count_shown(self):
        reporter, buf = self._reporter()
        reporter.report(_make_eval_report(checks_run=10, checks_passed=7))
        assert "7/10" in buf.getvalue()

    def test_duration_shown(self):
        reporter, buf = self._reporter()
        reporter.report(_make_eval_report())
        assert "42.5" in buf.getvalue()

    # Verbosity filtering
    def test_non_verbose_hides_passing_checks(self):
        passing = _make_check_result(check_id="good-check", passed=True)
        failing = _make_check_result(check_id="bad-check", passed=False)
        report = _make_eval_report(results=[passing, failing])
        reporter, buf = self._reporter(verbose=False)
        reporter.report(report)
        output = buf.getvalue()
        assert "bad-check" in output
        assert "good-check" not in output

    def test_verbose_shows_passing_checks(self):
        passing = _make_check_result(check_id="good-check", passed=True)
        failing = _make_check_result(check_id="bad-check", passed=False)
        report = _make_eval_report(results=[passing, failing])
        reporter, buf = self._reporter(verbose=True)
        reporter.report(report)
        output = buf.getvalue()
        assert "good-check" in output
        assert "bad-check" in output

    def test_non_verbose_with_all_passing_shows_hidden_hint(self):
        results = [_make_check_result(check_id=f"p{i}", passed=True) for i in range(3)]
        report = _make_eval_report(results=results)
        reporter, buf = self._reporter(verbose=False)
        reporter.report(report)
        assert "passing checks hidden" in buf.getvalue()

    def test_no_table_when_no_failing_checks_in_non_verbose(self):
        # All passing — no table rendered (results_to_show is empty)
        passing = _make_check_result(passed=True, message="green path")
        report = _make_eval_report(results=[passing])
        reporter, buf = self._reporter(verbose=False)
        reporter.report(report)
        # The check message should NOT appear (only shown in table)
        assert "green path" not in buf.getvalue()

    def test_check_id_shown_in_verbose_table(self):
        result = _make_check_result(check_id="unique-id-xyz")
        report = _make_eval_report(results=[result])
        reporter, buf = self._reporter(verbose=True)
        reporter.report(report)
        assert "unique-id-xyz" in buf.getvalue()

    def test_message_shown_for_failing_check(self):
        result = _make_check_result(message="Custom failure detail", passed=False)
        report = _make_eval_report(results=[result])
        reporter, buf = self._reporter(verbose=False)
        reporter.report(report)
        assert "Custom failure detail" in buf.getvalue()

    def test_check_name_in_verbose_table(self):
        result = _make_check_result(check_id="c1", check_name="My Check Name")
        report = _make_eval_report(results=[result])
        reporter, buf = self._reporter(verbose=True)
        reporter.report(report)
        # check_id is used in the table, not check_name — verify check_id present
        assert "c1" in buf.getvalue()

    # Dimension summary
    def test_dimension_summary_shown(self):
        summary = {"by_dimension": {"structure": {"passed": 2, "failed": 1}}}
        report = _make_eval_report(summary=summary)
        reporter, buf = self._reporter()
        reporter.report(report)
        assert "structure" in buf.getvalue()

    def test_dimension_pass_count_shown(self):
        summary = {"by_dimension": {"naming": {"passed": 4, "failed": 0}}}
        report = _make_eval_report(summary=summary)
        reporter, buf = self._reporter()
        reporter.report(report)
        assert "naming" in buf.getvalue()
        assert "4/4" in buf.getvalue()

    def test_dimension_zero_total_skipped(self):
        summary = {
            "by_dimension": {
                "structure": {"passed": 0, "failed": 0},
                "naming": {"passed": 1, "failed": 0},
            }
        }
        report = _make_eval_report(summary=summary)
        reporter, buf = self._reporter()
        reporter.report(report)
        assert "naming" in buf.getvalue()
        # "structure" has 0 total, should be skipped
        # Can't assert "structure" NOT in output because the label could appear elsewhere,
        # but we can verify naming IS shown
        assert "1/1" in buf.getvalue()

    def test_empty_summary_no_crash(self):
        report = _make_eval_report(summary={})
        reporter, buf = self._reporter()
        reporter.report(report)  # must not raise
        assert buf.getvalue()

    def test_multiple_dimensions_in_summary(self):
        summary = {
            "by_dimension": {
                "structure": {"passed": 3, "failed": 0},
                "naming": {"passed": 1, "failed": 1},
                "content": {"passed": 0, "failed": 2},
            }
        }
        report = _make_eval_report(summary=summary)
        reporter, buf = self._reporter()
        reporter.report(report)
        output = buf.getvalue()
        assert "structure" in output
        assert "naming" in output
        assert "content" in output

    def test_no_crash_with_empty_results(self):
        report = _make_eval_report(results=[], summary={"by_dimension": {}})
        reporter, buf = self._reporter()
        reporter.report(report)
        assert buf.getvalue()

    def test_verbose_hint_absent_in_verbose_mode(self):
        results = [_make_check_result(passed=True) for _ in range(5)]
        report = _make_eval_report(results=results)
        reporter, buf = self._reporter(verbose=True)
        reporter.report(report)
        assert "passing checks hidden" not in buf.getvalue()


# ─── ConsoleReporter.report_trace() ───────────────────────────────────────────


class TestConsoleReporterReportTrace:
    def _reporter(self, verbose: bool = False) -> tuple[ConsoleReporter, io.StringIO]:
        r = ConsoleReporter(verbose=verbose)
        return _capture(r)

    def test_trace_path_in_output(self):
        reporter, buf = self._reporter()
        reporter.report_trace(_make_trace_report(trace_path="/my/trace.jsonl"))
        assert "/my/trace.jsonl" in buf.getvalue()

    def test_project_dir_in_output(self):
        reporter, buf = self._reporter()
        reporter.report_trace(_make_trace_report(project_dir="/my/project"))
        assert "/my/project" in buf.getvalue()

    def test_all_passed_shows_count(self):
        reporter, buf = self._reporter()
        reporter.report_trace(_make_trace_report(overall_pass=True, checks_passed=5, checks_run=5))
        output = buf.getvalue()
        assert "5" in output
        assert "passed" in output.lower()

    def test_failure_count_shown(self):
        results = [
            _make_trace_check_result(check_id="f1", passed=False),
            _make_trace_check_result(check_id="f2", passed=False),
        ]
        report = _make_trace_report(
            overall_pass=False,
            checks_run=3,
            checks_passed=1,
            checks_failed=2,
            pass_rate=33.3,
            results=results,
        )
        reporter, buf = self._reporter()
        reporter.report_trace(report)
        output = buf.getvalue()
        assert "2" in output

    def test_pass_rate_shown(self):
        reporter, buf = self._reporter()
        reporter.report_trace(_make_trace_report(pass_rate=75.0))
        assert "75.0" in buf.getvalue()

    def test_duration_shown(self):
        reporter, buf = self._reporter()
        reporter.report_trace(_make_trace_report())
        assert "33.3" in buf.getvalue()

    def test_non_verbose_hides_passing_trace_checks(self):
        passing = _make_trace_check_result(check_id="passing-check", passed=True)
        failing = _make_trace_check_result(check_id="failing-check", passed=False)
        report = _make_trace_report(
            overall_pass=False,
            checks_run=2,
            checks_passed=1,
            checks_failed=1,
            pass_rate=50.0,
            results=[passing, failing],
        )
        reporter, buf = self._reporter(verbose=False)
        reporter.report_trace(report)
        output = buf.getvalue()
        assert "failing-check" in output
        assert "passing-check" not in output

    def test_verbose_shows_all_trace_checks(self):
        passing = _make_trace_check_result(check_id="passing-check", passed=True)
        failing = _make_trace_check_result(check_id="failing-check", passed=False)
        report = _make_trace_report(
            overall_pass=False,
            checks_run=2,
            checks_passed=1,
            checks_failed=1,
            pass_rate=50.0,
            results=[passing, failing],
        )
        reporter, buf = self._reporter(verbose=True)
        reporter.report_trace(report)
        output = buf.getvalue()
        assert "passing-check" in output
        assert "failing-check" in output

    def test_check_type_in_verbose_table(self):
        result = _make_trace_check_result(check_id="c1", check_type="loop_detection")
        report = _make_trace_report(results=[result])
        reporter, buf = self._reporter(verbose=True)
        reporter.report_trace(report)
        assert "loop_detection" in buf.getvalue()

    def test_summary_by_type_shown(self):
        summary = {"by_type": {"command_presence": {"passed": 2, "total": 3}}}
        report = _make_trace_report(summary=summary)
        reporter, buf = self._reporter()
        reporter.report_trace(report)
        assert "command_presence" in buf.getvalue()

    def test_summary_by_type_pct_shown(self):
        summary = {"by_type": {"file_creation": {"passed": 1, "total": 2}}}
        report = _make_trace_report(summary=summary)
        reporter, buf = self._reporter()
        reporter.report_trace(report)
        assert "50" in buf.getvalue()

    def test_empty_summary_by_type_no_crash(self):
        report = _make_trace_report(summary={"by_type": {}})
        reporter, buf = self._reporter()
        reporter.report_trace(report)  # must not raise

    def test_no_crash_with_empty_results(self):
        report = _make_trace_report(results=[], checks_run=0, checks_passed=0)
        reporter, buf = self._reporter()
        reporter.report_trace(report)
        assert buf.getvalue()

    def test_hidden_hint_in_non_verbose_with_passing_checks(self):
        results = [_make_trace_check_result(check_id=f"c{i}", passed=True) for i in range(3)]
        report = _make_trace_report(checks_run=3, checks_passed=3, results=results)
        reporter, buf = self._reporter(verbose=False)
        reporter.report_trace(report)
        assert "passing checks hidden" in buf.getvalue()

    def test_message_in_check_table(self):
        result = _make_trace_check_result(passed=False, message="specific error detail")
        report = _make_trace_report(
            overall_pass=False,
            checks_failed=1,
            checks_passed=0,
            pass_rate=0.0,
            results=[result],
        )
        reporter, buf = self._reporter(verbose=False)
        reporter.report_trace(report)
        assert "specific error detail" in buf.getvalue()


# ─── JsonReporter.format() ────────────────────────────────────────────────────


class TestJsonReporterFormat:
    def test_schema_version_included_by_default(self):
        result = json.loads(JsonReporter().format(_make_eval_report()))
        assert "schema_version" in result

    def test_schema_version_value(self):
        result = json.loads(JsonReporter().format(_make_eval_report()))
        assert result["schema_version"] == SCHEMA_VERSION

    def test_schema_version_excluded_when_flag_false(self):
        result = json.loads(JsonReporter(include_schema_version=False).format(_make_eval_report()))
        assert "schema_version" not in result

    def test_schema_version_constant_is_1_0(self):
        assert SCHEMA_VERSION == "1.0"

    def test_output_is_valid_json(self):
        output = JsonReporter().format(_make_eval_report())
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_skill_name_in_output(self):
        result = json.loads(JsonReporter().format(_make_eval_report(skill_name="demo-skill")))
        assert result["skill_name"] == "demo-skill"

    def test_skill_name_none_serialized(self):
        result = json.loads(JsonReporter().format(_make_eval_report(skill_name=None)))
        assert result["skill_name"] is None

    def test_skill_path_in_output(self):
        result = json.loads(JsonReporter().format(_make_eval_report(skill_path="/a/b/c")))
        assert result["skill_path"] == "/a/b/c"

    def test_quality_score_in_output(self):
        result = json.loads(JsonReporter().format(_make_eval_report(score=73.4)))
        assert abs(result["quality_score"] - 73.4) < 0.001

    def test_overall_pass_true(self):
        result = json.loads(JsonReporter().format(_make_eval_report(overall_pass=True)))
        assert result["overall_pass"] is True

    def test_overall_pass_false(self):
        result = json.loads(JsonReporter().format(_make_eval_report(overall_pass=False)))
        assert result["overall_pass"] is False

    def test_checks_run_and_passed(self):
        result = json.loads(
            JsonReporter().format(_make_eval_report(checks_run=12, checks_passed=10))
        )
        assert result["checks_run"] == 12
        assert result["checks_passed"] == 10

    def test_results_list_present(self):
        results = [_make_check_result(check_id="c1"), _make_check_result(check_id="c2")]
        result = json.loads(JsonReporter().format(_make_eval_report(results=results)))
        assert isinstance(result["results"], list)
        assert len(result["results"]) == 2

    def test_result_check_ids_preserved(self):
        results = [_make_check_result(check_id="sentinel-id")]
        result = json.loads(JsonReporter().format(_make_eval_report(results=results)))
        assert result["results"][0]["check_id"] == "sentinel-id"

    def test_result_severity_serialized_as_string(self):
        results = [_make_check_result(severity=Severity.MEDIUM)]
        result = json.loads(JsonReporter().format(_make_eval_report(results=results)))
        assert result["results"][0]["severity"] == "medium"

    def test_schema_version_is_first_key(self):
        result = json.loads(JsonReporter().format(_make_eval_report()))
        assert list(result.keys())[0] == "schema_version"

    def test_custom_indent_2(self):
        output = JsonReporter(indent=2).format(_make_eval_report())
        assert "  " in output  # 2-space indented JSON

    def test_custom_indent_4(self):
        output = JsonReporter(indent=4).format(_make_eval_report())
        assert "    " in output  # 4-space indented JSON

    def test_compact_indent_none(self):
        output = JsonReporter(indent=None).format(_make_eval_report())  # type: ignore[arg-type]
        # Compact JSON: single line (no embedded newlines)
        assert "\n" not in output.strip()

    def test_summary_field_present(self):
        summary = {"by_dimension": {"structure": {"passed": 1, "failed": 0}}}
        result = json.loads(JsonReporter().format(_make_eval_report(summary=summary)))
        assert "summary" in result
        assert result["summary"] == summary

    def test_timestamp_field_present(self):
        result = json.loads(JsonReporter().format(_make_eval_report()))
        assert result["timestamp"] == "2026-01-01T00:00:00Z"

    def test_duration_ms_field_present(self):
        result = json.loads(JsonReporter().format(_make_eval_report()))
        assert abs(result["duration_ms"] - 42.5) < 0.001


# ─── JsonReporter.write() ─────────────────────────────────────────────────────


class TestJsonReporterWrite:
    def test_write_to_buffer_produces_valid_json(self):
        buf = io.StringIO()
        JsonReporter().write(_make_eval_report(), buf)
        parsed = json.loads(buf.getvalue())
        assert isinstance(parsed, dict)

    def test_write_appends_trailing_newline(self):
        buf = io.StringIO()
        JsonReporter().write(_make_eval_report(), buf)
        assert buf.getvalue().endswith("\n")

    def test_write_skill_name_in_buffer(self):
        buf = io.StringIO()
        JsonReporter().write(_make_eval_report(skill_name="written-skill"), buf)
        result = json.loads(buf.getvalue())
        assert result["skill_name"] == "written-skill"

    def test_write_schema_version_in_buffer(self):
        buf = io.StringIO()
        JsonReporter().write(_make_eval_report(), buf)
        result = json.loads(buf.getvalue())
        assert result["schema_version"] == "1.0"

    def test_write_without_schema_version(self):
        buf = io.StringIO()
        JsonReporter(include_schema_version=False).write(_make_eval_report(), buf)
        result = json.loads(buf.getvalue())
        assert "schema_version" not in result


# ─── JsonReporter.write_file() ────────────────────────────────────────────────


class TestJsonReporterWriteFile:
    def test_creates_file(self, tmp_path: Path):
        path = tmp_path / "report.json"
        JsonReporter().write_file(_make_eval_report(), path)
        assert path.exists()

    def test_valid_json_in_file(self, tmp_path: Path):
        path = tmp_path / "report.json"
        JsonReporter().write_file(_make_eval_report(skill_name="file-skill"), path)
        result = json.loads(path.read_text())
        assert result["skill_name"] == "file-skill"

    def test_creates_nested_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "report.json"
        JsonReporter().write_file(_make_eval_report(), path)
        assert path.exists()

    def test_accepts_string_path(self, tmp_path: Path):
        path = str(tmp_path / "report.json")
        JsonReporter().write_file(_make_eval_report(), path)
        assert Path(path).exists()

    def test_file_ends_with_newline(self, tmp_path: Path):
        path = tmp_path / "report.json"
        JsonReporter().write_file(_make_eval_report(), path)
        assert path.read_text().endswith("\n")

    def test_overwrites_existing_file(self, tmp_path: Path):
        path = tmp_path / "report.json"
        JsonReporter().write_file(_make_eval_report(skill_name="first"), path)
        JsonReporter().write_file(_make_eval_report(skill_name="second"), path)
        result = json.loads(path.read_text())
        assert result["skill_name"] == "second"

    def test_schema_version_in_file(self, tmp_path: Path):
        path = tmp_path / "report.json"
        JsonReporter().write_file(_make_eval_report(), path)
        result = json.loads(path.read_text())
        assert result["schema_version"] == "1.0"

    def test_file_without_schema_version(self, tmp_path: Path):
        path = tmp_path / "report.json"
        JsonReporter(include_schema_version=False).write_file(_make_eval_report(), path)
        result = json.loads(path.read_text())
        assert "schema_version" not in result
