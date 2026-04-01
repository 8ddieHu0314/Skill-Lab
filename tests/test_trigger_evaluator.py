"""Unit tests for skill_lab.triggers.trigger_evaluator.TriggerEvaluator."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skill_lab.core.models import (
    TraceEvent,
    TriggerExpectation,
    TriggerReport,
    TriggerResult,
    TriggerTestCase,
    TriggerType,
)
from skill_lab.providers.base import ExecutionContext, ExecutionProvider
from skill_lab.providers.local import LocalProvider
from skill_lab.runtimes.base import RuntimeAdapter
from skill_lab.triggers.trigger_evaluator import TriggerEvaluator


# ─── Test doubles ─────────────────────────────────────────────────────────────


class FakeRuntime(RuntimeAdapter):
    """Deterministic runtime for unit tests — never calls any CLI."""

    def __init__(
        self,
        name_: str = "fake",
        available: bool = True,
        exit_code: int = 0,
        events: list[TraceEvent] | None = None,
    ) -> None:
        self._name = name_
        self._available = available
        self._exit_code = exit_code
        self._events: list[TraceEvent] = events or []

    @property
    def name(self) -> str:
        return self._name

    def _cli_binary_name(self) -> str:
        return "fake"

    def _build_command(self, cli_path: str, prompt: str) -> list[str]:
        return [cli_path, prompt]

    def _check_skill_trigger(self, line: str, skill_name: str) -> bool:
        return False

    def is_available(self) -> bool:
        return self._available

    def execute(
        self,
        prompt: str,
        skill_path: Path,
        trace_path: Path,
        stop_on_skill: str | None = None,
        working_dir: Path | None = None,
    ) -> int:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text("")
        return self._exit_code

    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]:
        return iter(self._events)


class MockAnalyzer:
    """Lightweight stand-in for TraceAnalyzer with configurable answers."""

    def __init__(
        self,
        skill_triggered: bool = True,
        commands_run: list[str] | None = None,
        files_exist: list[str] | None = None,
        has_loops: bool = False,
    ) -> None:
        self._skill_triggered = skill_triggered
        self._commands_run = set(commands_run or [])
        self._files_exist = set(files_exist or [])
        self._has_loops = has_loops

    def skill_was_triggered(self, name: str) -> bool:
        return self._skill_triggered

    def command_was_run(self, pattern: str) -> bool:
        return any(pattern in cmd for cmd in self._commands_run)

    def file_was_created(self, filepath: str, project_dir: Path) -> bool:
        return filepath in self._files_exist

    def detect_loops(self) -> bool:
        return self._has_loops


class FakeProvider(ExecutionProvider):
    """Deterministic provider for unit tests — passes through to runtime."""

    def __init__(self) -> None:
        self.setup_called = False
        self.teardown_called = False
        self.prepare_count = 0
        self.cleanup_count = 0

    @property
    def name(self) -> str:
        return "fake"

    def setup(self, skill_path: Path, skill_name: str) -> None:
        self.setup_called = True

    def prepare_test(
        self, skill_path: Path, skill_name: str, trace_path: Path
    ) -> ExecutionContext:
        self.prepare_count += 1
        return ExecutionContext(
            skill_path=skill_path,
            skill_name=skill_name,
            working_dir=skill_path,
            trace_path=trace_path,
        )

    def execute(
        self,
        context: ExecutionContext,
        runtime: RuntimeAdapter,
        prompt: str,
        stop_on_skill: str | None,
    ) -> int:
        return runtime.execute(
            prompt=prompt,
            skill_path=context.skill_path,
            trace_path=context.trace_path,
            stop_on_skill=stop_on_skill,
            working_dir=context.working_dir,
        )

    def collect_trace(self, context: ExecutionContext) -> Path:
        return context.trace_path

    def cleanup_test(self, context: ExecutionContext) -> None:
        self.cleanup_count += 1

    def teardown(self) -> None:
        self.teardown_called = True


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_test_case(
    id: str = "test-1",
    name: str = "Test One",
    skill_name: str = "my-skill",
    prompt: str = "do something",
    trigger_type: TriggerType = TriggerType.EXPLICIT,
    skill_triggered: bool = True,
    exit_code: int | None = None,
    commands_include: tuple[str, ...] = (),
    files_created: tuple[str, ...] = (),
    no_loops: bool = False,
) -> TriggerTestCase:
    return TriggerTestCase(
        id=id,
        name=name,
        skill_name=skill_name,
        prompt=prompt,
        trigger_type=trigger_type,
        expected=TriggerExpectation(
            skill_triggered=skill_triggered,
            exit_code=exit_code,
            commands_include=commands_include,
            files_created=files_created,
            no_loops=no_loops,
        ),
    )


def _make_trigger_result(
    passed: bool = True, trigger_type: TriggerType = TriggerType.EXPLICIT
) -> TriggerResult:
    return TriggerResult(
        test_id="t1",
        test_name="T1",
        trigger_type=trigger_type,
        passed=passed,
        skill_triggered=passed,
        expected_trigger=True,
        message="ok" if passed else "fail",
    )


# ─── _get_runtime ─────────────────────────────────────────────────────────────


class TestGetRuntime:
    def test_codex_runtime_selected_by_name(self):
        evaluator = TriggerEvaluator(runtime="codex")
        with patch("skill_lab.triggers.trigger_evaluator.CodexRuntime") as MockCodex:
            evaluator._get_runtime()
            MockCodex.assert_called_once()

    def test_claude_runtime_selected_by_name(self):
        evaluator = TriggerEvaluator(runtime="claude")
        with patch("skill_lab.triggers.trigger_evaluator.ClaudeRuntime") as MockClaude:
            evaluator._get_runtime()
            MockClaude.assert_called_once()

    def test_auto_detect_uses_codex_when_available(self):
        evaluator = TriggerEvaluator(runtime=None)
        with (
            patch("skill_lab.triggers.trigger_evaluator.CodexRuntime") as MockCodex,
            patch("skill_lab.triggers.trigger_evaluator.ClaudeRuntime"),
        ):
            mock_codex_instance = MockCodex.return_value
            mock_codex_instance.is_available.return_value = True
            runtime = evaluator._get_runtime()
            assert runtime is mock_codex_instance

    def test_auto_detect_falls_back_to_claude_when_codex_unavailable(self):
        evaluator = TriggerEvaluator(runtime=None)
        with (
            patch("skill_lab.triggers.trigger_evaluator.CodexRuntime") as MockCodex,
            patch("skill_lab.triggers.trigger_evaluator.ClaudeRuntime") as MockClaude,
        ):
            MockCodex.return_value.is_available.return_value = False
            MockClaude.return_value.is_available.return_value = True
            runtime = evaluator._get_runtime()
            assert runtime is MockClaude.return_value

    def test_auto_detect_defaults_to_codex_when_neither_available(self):
        evaluator = TriggerEvaluator(runtime=None)
        with (
            patch("skill_lab.triggers.trigger_evaluator.CodexRuntime") as MockCodex,
            patch("skill_lab.triggers.trigger_evaluator.ClaudeRuntime") as MockClaude,
        ):
            MockCodex.return_value.is_available.return_value = False
            MockClaude.return_value.is_available.return_value = False
            runtime = evaluator._get_runtime()
            # Falls back to codex even when unavailable
            assert runtime is MockCodex.return_value


# ─── _get_skill_name ──────────────────────────────────────────────────────────


class TestGetSkillName:
    def test_returns_skill_name_from_first_test_case(self, tmp_path: Path):
        evaluator = TriggerEvaluator()
        tc = _make_test_case(skill_name="report-skill")
        assert evaluator._get_skill_name(tmp_path / "skill", [tc]) == "report-skill"

    def test_skips_unknown_skill_name(self, tmp_path: Path):
        evaluator = TriggerEvaluator()
        tc_unknown = _make_test_case(skill_name="unknown")
        tc_real = _make_test_case(skill_name="real-skill")
        result = evaluator._get_skill_name(tmp_path / "skill", [tc_unknown, tc_real])
        assert result == "real-skill"

    def test_falls_back_to_path_name_when_no_test_cases(self, tmp_path: Path):
        evaluator = TriggerEvaluator()
        skill_path = tmp_path / "my-fallback-skill"
        assert evaluator._get_skill_name(skill_path, []) == "my-fallback-skill"

    def test_falls_back_to_path_name_when_all_unknown(self, tmp_path: Path):
        evaluator = TriggerEvaluator()
        tcs = [_make_test_case(skill_name="unknown"), _make_test_case(skill_name="unknown")]
        skill_path = tmp_path / "path-skill"
        assert evaluator._get_skill_name(skill_path, tcs) == "path-skill"

    def test_returns_first_non_unknown_name(self, tmp_path: Path):
        evaluator = TriggerEvaluator()
        tcs = [
            _make_test_case(skill_name="unknown"),
            _make_test_case(skill_name="first-real"),
            _make_test_case(skill_name="second-real"),
        ]
        assert evaluator._get_skill_name(tmp_path / "x", tcs) == "first-real"


# ─── _check_expectations ──────────────────────────────────────────────────────


class TestCheckExpectations:
    """Test the expectations logic with a mock analyzer."""

    def _evaluator(self) -> TriggerEvaluator:
        return TriggerEvaluator()

    def _check(
        self,
        skill_triggered: bool = True,
        expected_triggered: bool = True,
        exit_code_actual: int = 0,
        exit_code_expected: int | None = None,
        commands_include: tuple[str, ...] = (),
        commands_run: list[str] | None = None,
        files_created_expected: tuple[str, ...] = (),
        files_exist: list[str] | None = None,
        no_loops: bool = False,
        has_loops: bool = False,
    ) -> bool:
        evaluator = self._evaluator()
        test_case = _make_test_case(
            skill_triggered=expected_triggered,
            exit_code=exit_code_expected,
            commands_include=commands_include,
            files_created=files_created_expected,
            no_loops=no_loops,
        )
        analyzer = MockAnalyzer(
            skill_triggered=skill_triggered,
            commands_run=commands_run,
            files_exist=files_exist,
            has_loops=has_loops,
        )
        return evaluator._check_expectations(
            test_case,
            analyzer,  # type: ignore[arg-type]
            Path("/fake/skill"),
            skill_triggered,
            exit_code_actual,
        )

    # Skill trigger expectation
    @pytest.mark.parametrize(
        "skill_triggered, expected_triggered, want",
        [
            (True, True, True),
            (False, False, True),
            (False, True, False),
            (True, False, False),
        ],
        ids=["match", "negative-match", "not-triggered", "unexpected-trigger"],
    )
    def test_skill_trigger_expectation(self, skill_triggered, expected_triggered, want):
        assert (
            self._check(skill_triggered=skill_triggered, expected_triggered=expected_triggered)
            is want
        )

    # Exit code
    @pytest.mark.parametrize(
        "exit_code_actual, exit_code_expected, want",
        [
            (1, None, True),
            (0, 0, True),
            (1, 0, False),
            (2, 2, True),
        ],
        ids=["not-specified", "matches", "mismatches", "nonzero-matches"],
    )
    def test_exit_code_expectation(self, exit_code_actual, exit_code_expected, want):
        assert (
            self._check(exit_code_actual=exit_code_actual, exit_code_expected=exit_code_expected)
            is want
        )

    # Command inclusion
    @pytest.mark.parametrize(
        "commands_include, commands_run, want",
        [
            (("npm install",), ["npm install", "npm test"], True),
            (("npm test",), ["npm install"], False),
            (("npm install", "npm test"), ["npm install"], False),
            (("cmd-a", "cmd-b"), ["cmd-a", "cmd-b", "cmd-c"], True),
            ((), [], True),
        ],
        ids=["present", "missing", "one-missing", "all-present", "none-required"],
    )
    def test_command_inclusion(self, commands_include, commands_run, want):
        assert self._check(commands_include=commands_include, commands_run=commands_run) is want

    # File creation
    @pytest.mark.parametrize(
        "files_created_expected, files_exist, want",
        [
            (("output.txt",), ["output.txt"], True),
            (("report.pdf",), [], False),
            (("a.txt", "b.txt"), ["a.txt"], False),
            (("a.txt", "b.txt"), ["a.txt", "b.txt"], True),
            ((), [], True),
        ],
        ids=["present", "missing", "one-missing", "all-present", "none-required"],
    )
    def test_file_creation(self, files_created_expected, files_exist, want):
        assert (
            self._check(files_created_expected=files_created_expected, files_exist=files_exist)
            is want
        )

    # Loop detection
    @pytest.mark.parametrize(
        "no_loops, has_loops, want",
        [
            (True, True, False),
            (True, False, True),
            (False, True, True),
        ],
        ids=["loops-detected", "no-loops", "ignored"],
    )
    def test_loop_detection(self, no_loops, has_loops, want):
        assert self._check(no_loops=no_loops, has_loops=has_loops) is want

    # Combined scenarios
    def test_all_expectations_pass(self):
        assert (
            self._check(
                skill_triggered=True,
                expected_triggered=True,
                exit_code_actual=0,
                exit_code_expected=0,
                commands_include=("npm install",),
                commands_run=["npm install"],
                files_created_expected=("dist/output.js",),
                files_exist=["dist/output.js"],
                no_loops=True,
                has_loops=False,
            )
            is True
        )

    def test_one_failure_causes_overall_false(self):
        # Everything passes but exit code mismatches
        assert (
            self._check(
                skill_triggered=True,
                expected_triggered=True,
                exit_code_actual=1,
                exit_code_expected=0,
                commands_include=("npm install",),
                commands_run=["npm install"],
            )
            is False
        )


# ─── _run_single_test ─────────────────────────────────────────────────────────


class TestRunSingleTest:
    def _make_evaluator(self, tmp_path: Path) -> TriggerEvaluator:
        evaluator = TriggerEvaluator()
        evaluator._trace_dir = tmp_path / ".sklab" / "traces"
        return evaluator

    def test_returns_passing_result_when_expectations_met(self, tmp_path: Path):
        skill_path = tmp_path / "skill"
        skill_path.mkdir()
        # Provide a skill invocation event so skill_was_triggered returns True
        events = [
            TraceEvent(
                type="item.started",
                item_type="skill_invocation",
                command="$my-skill run",
                raw={},
            )
        ]
        runtime = FakeRuntime(events=events)
        evaluator = self._make_evaluator(tmp_path)
        provider = FakeProvider()

        test_case = _make_test_case(skill_name="my-skill", skill_triggered=True)
        result = evaluator._run_single_test(test_case, skill_path, runtime, provider)
        assert isinstance(result, TriggerResult)
        assert result.test_id == "test-1"

    def test_returns_result_with_trace_path(self, tmp_path: Path):
        skill_path = tmp_path / "skill"
        skill_path.mkdir()
        runtime = FakeRuntime()
        evaluator = self._make_evaluator(tmp_path)
        provider = FakeProvider()

        test_case = _make_test_case(id="my-test", skill_triggered=False)
        result = evaluator._run_single_test(test_case, skill_path, runtime, provider)
        assert result.trace_path is not None
        assert "my-test.jsonl" in str(result.trace_path)

    def test_creates_trace_directory(self, tmp_path: Path):
        skill_path = tmp_path / "skill"
        skill_path.mkdir()
        evaluator = TriggerEvaluator()
        evaluator._trace_dir = tmp_path / "traces" / "nested"
        provider = FakeProvider()

        evaluator._run_single_test(_make_test_case(), skill_path, FakeRuntime(), provider)
        assert evaluator._trace_dir.exists()

    def test_handles_runtime_exception_gracefully(self, tmp_path: Path):
        skill_path = tmp_path / "skill"
        skill_path.mkdir()

        class BrokenRuntime(FakeRuntime):
            def execute(self, *args, **kwargs) -> int:
                raise RuntimeError("CLI not found")

        evaluator = self._make_evaluator(tmp_path)
        provider = FakeProvider()

        result = evaluator._run_single_test(
            _make_test_case(), skill_path, BrokenRuntime(), provider
        )
        assert result.passed is False
        assert "CLI not found" in result.message or "execution failed" in result.message.lower()

    def test_result_includes_events_count(self, tmp_path: Path):
        skill_path = tmp_path / "skill"
        skill_path.mkdir()
        events = [
            TraceEvent(type="item.completed", raw={}),
            TraceEvent(type="item.completed", raw={}),
        ]
        runtime = FakeRuntime(events=events)
        evaluator = self._make_evaluator(tmp_path)
        provider = FakeProvider()

        result = evaluator._run_single_test(
            _make_test_case(skill_triggered=False), skill_path, runtime, provider
        )
        assert result.events_count == 2

    def test_result_includes_exit_code(self, tmp_path: Path):
        skill_path = tmp_path / "skill"
        skill_path.mkdir()
        runtime = FakeRuntime(exit_code=42)
        evaluator = self._make_evaluator(tmp_path)
        provider = FakeProvider()

        result = evaluator._run_single_test(
            _make_test_case(skill_triggered=False), skill_path, runtime, provider
        )
        assert result.exit_code == 42

    def test_provider_working_dir_used(self, tmp_path: Path):
        """The provider's working_dir is passed to the runtime."""
        skill_path = tmp_path / "skill"
        skill_path.mkdir()

        recorded: list[Path | None] = []

        class RecordingRuntime(FakeRuntime):
            def execute(
                self, prompt, skill_path, trace_path, stop_on_skill=None, working_dir=None
            ) -> int:
                recorded.append(working_dir)
                trace_path.parent.mkdir(parents=True, exist_ok=True)
                trace_path.write_text("")
                return 0

        evaluator = self._make_evaluator(tmp_path)
        provider = FakeProvider()
        evaluator._run_single_test(_make_test_case(), skill_path, RecordingRuntime(), provider)
        # FakeProvider sets working_dir = skill_path
        assert recorded[0] == skill_path

    def test_cleanup_called_after_test(self, tmp_path: Path):
        skill_path = tmp_path / "skill"
        skill_path.mkdir()
        evaluator = self._make_evaluator(tmp_path)
        provider = FakeProvider()

        evaluator._run_single_test(_make_test_case(), skill_path, FakeRuntime(), provider)
        assert provider.cleanup_count == 1

    def test_cleanup_called_on_exception(self, tmp_path: Path):
        skill_path = tmp_path / "skill"
        skill_path.mkdir()

        class BrokenRuntime(FakeRuntime):
            def execute(self, *args, **kwargs) -> int:
                raise RuntimeError("boom")

        evaluator = self._make_evaluator(tmp_path)
        provider = FakeProvider()

        evaluator._run_single_test(_make_test_case(), skill_path, BrokenRuntime(), provider)
        assert provider.cleanup_count == 1


# ─── evaluate() ───────────────────────────────────────────────────────────────


class TestEvaluate:
    """High-level evaluate() tests with mocked load_trigger_tests and runtime."""

    _PATCH_LOAD = "skill_lab.triggers.trigger_evaluator.load_trigger_tests"

    def _evaluator_with_runtime(self, runtime: FakeRuntime | None = None) -> TriggerEvaluator:
        ev = TriggerEvaluator()
        if runtime is None:
            runtime = FakeRuntime()
        ev._get_runtime = lambda: runtime  # type: ignore[method-assign]
        return ev

    def test_returns_trigger_report(self, tmp_path: Path):
        tc = _make_test_case(skill_triggered=False)
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=([tc], [])):
            with patch.object(ev, "_run_single_test", return_value=_make_trigger_result()):
                report = ev.evaluate(tmp_path / "skill")
        assert isinstance(report, TriggerReport)

    def test_report_includes_skill_name(self, tmp_path: Path):
        tc = _make_test_case(skill_name="special-skill")
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=([tc], [])):
            with patch.object(ev, "_run_single_test", return_value=_make_trigger_result()):
                report = ev.evaluate(tmp_path / "skill")
        assert report.skill_name == "special-skill"

    def test_report_overall_pass_when_all_pass(self, tmp_path: Path):
        tcs = [_make_test_case(id=f"t{i}") for i in range(3)]
        results = [_make_trigger_result(passed=True) for _ in tcs]
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            with patch.object(ev, "_run_single_test", side_effect=results):
                report = ev.evaluate(tmp_path / "skill")
        assert report.overall_pass is True

    def test_report_overall_fail_when_any_fail(self, tmp_path: Path):
        tcs = [_make_test_case(id="t1"), _make_test_case(id="t2")]
        results = [_make_trigger_result(passed=True), _make_trigger_result(passed=False)]
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            with patch.object(ev, "_run_single_test", side_effect=results):
                report = ev.evaluate(tmp_path / "skill")
        assert report.overall_pass is False

    def test_report_tests_run_count(self, tmp_path: Path):
        tcs = [_make_test_case(id=f"t{i}") for i in range(4)]
        results = [_make_trigger_result() for _ in tcs]
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            with patch.object(ev, "_run_single_test", side_effect=results):
                report = ev.evaluate(tmp_path / "skill")
        assert report.tests_run == 4

    def test_report_tests_passed_count(self, tmp_path: Path):
        tcs = [_make_test_case(id=f"t{i}") for i in range(3)]
        results = [
            _make_trigger_result(passed=True),
            _make_trigger_result(passed=False),
            _make_trigger_result(passed=True),
        ]
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            with patch.object(ev, "_run_single_test", side_effect=results):
                report = ev.evaluate(tmp_path / "skill")
        assert report.tests_passed == 2
        assert report.tests_failed == 1

    def test_report_runtime_name(self, tmp_path: Path):
        tc = _make_test_case()
        ev = self._evaluator_with_runtime(FakeRuntime(name_="codex"))
        with patch(self._PATCH_LOAD, return_value=([tc], [])):
            with patch.object(ev, "_run_single_test", return_value=_make_trigger_result()):
                report = ev.evaluate(tmp_path / "skill")
        assert report.runtime == "codex"

    def test_report_skill_path_is_string(self, tmp_path: Path):
        skill_path = tmp_path / "my-skill"
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=([], [])):
            report = ev.evaluate(skill_path)
        assert report.skill_path == str(skill_path)

    def test_report_has_results_list(self, tmp_path: Path):
        tcs = [_make_test_case(id=f"t{i}") for i in range(2)]
        results = [_make_trigger_result() for _ in tcs]
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            with patch.object(ev, "_run_single_test", side_effect=results):
                report = ev.evaluate(tmp_path / "skill")
        assert len(report.results) == 2

    def test_load_errors_reported_when_no_tests(self, tmp_path: Path):
        ev = self._evaluator_with_runtime()
        errors = ["No .sklab/tests/ directory found"]
        with patch(self._PATCH_LOAD, return_value=([], errors)):
            report = ev.evaluate(tmp_path / "skill")
        assert report.tests_run == 1  # one error result
        assert report.overall_pass is False
        assert report.results[0].test_id == "load-error"
        assert "No .sklab/tests" in report.results[0].message

    def test_multiple_load_errors_create_multiple_results(self, tmp_path: Path):
        ev = self._evaluator_with_runtime()
        errors = ["Error A", "Error B"]
        with patch(self._PATCH_LOAD, return_value=([], errors)):
            report = ev.evaluate(tmp_path / "skill")
        assert report.tests_run == 2
        messages = [r.message for r in report.results]
        assert "Error A" in messages
        assert "Error B" in messages

    def test_type_filter_applied(self, tmp_path: Path):
        explicit_tc = _make_test_case(id="e1", trigger_type=TriggerType.EXPLICIT)
        implicit_tc = _make_test_case(id="i1", trigger_type=TriggerType.IMPLICIT)
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=([explicit_tc, implicit_tc], [])):
            with patch.object(
                ev, "_run_single_test", return_value=_make_trigger_result()
            ) as mock_run:
                ev.evaluate(tmp_path / "skill", type_filter=TriggerType.EXPLICIT)
                # Only explicit test was run
                assert mock_run.call_count == 1
                called_tc = mock_run.call_args[0][0]
                assert called_tc.id == "e1"

    def test_type_filter_negative_only(self, tmp_path: Path):
        tcs = [
            _make_test_case(id="e", trigger_type=TriggerType.EXPLICIT),
            _make_test_case(id="n", trigger_type=TriggerType.NEGATIVE),
        ]
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            with patch.object(
                ev, "_run_single_test", return_value=_make_trigger_result()
            ) as mock_run:
                ev.evaluate(tmp_path / "skill", type_filter=TriggerType.NEGATIVE)
                assert mock_run.call_count == 1
                assert mock_run.call_args[0][0].id == "n"

    def test_progress_callback_called_for_each_test(self, tmp_path: Path):
        tcs = [_make_test_case(id=f"t{i}", name=f"Test {i}") for i in range(3)]
        ev = self._evaluator_with_runtime()
        calls: list[tuple] = []
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            with patch.object(ev, "_run_single_test", return_value=_make_trigger_result()):
                ev.evaluate(
                    tmp_path / "skill", progress_callback=lambda c, t, n: calls.append((c, t, n))
                )
        assert len(calls) == 3
        assert calls[0] == (1, 3, "Test 0")
        assert calls[1] == (2, 3, "Test 1")
        assert calls[2] == (3, 3, "Test 2")

    def test_progress_callback_none_does_not_crash(self, tmp_path: Path):
        tc = _make_test_case()
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=([tc], [])):
            with patch.object(ev, "_run_single_test", return_value=_make_trigger_result()):
                ev.evaluate(tmp_path / "skill", progress_callback=None)  # must not raise

    def test_report_pass_rate_all_pass(self, tmp_path: Path):
        tcs = [_make_test_case(id=f"t{i}") for i in range(4)]
        results = [_make_trigger_result(passed=True) for _ in tcs]
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            with patch.object(ev, "_run_single_test", side_effect=results):
                report = ev.evaluate(tmp_path / "skill")
        # pass_rate is stored as 0-1 range (converted from percentage)
        assert abs(report.pass_rate - 1.0) < 0.001

    def test_report_pass_rate_none_pass(self, tmp_path: Path):
        tcs = [_make_test_case(id="t1")]
        results = [_make_trigger_result(passed=False)]
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            with patch.object(ev, "_run_single_test", side_effect=results):
                report = ev.evaluate(tmp_path / "skill")
        assert abs(report.pass_rate - 0.0) < 0.001

    def test_report_pass_rate_zero_when_no_tests(self, tmp_path: Path):
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=([], [])):
            report = ev.evaluate(tmp_path / "skill")
        assert report.pass_rate == 0.0

    def test_report_summary_by_type_built(self, tmp_path: Path):
        tcs = [
            _make_test_case(id="e1", trigger_type=TriggerType.EXPLICIT),
            _make_test_case(id="i1", trigger_type=TriggerType.IMPLICIT),
        ]
        results = [
            _make_trigger_result(trigger_type=TriggerType.EXPLICIT),
            _make_trigger_result(trigger_type=TriggerType.IMPLICIT),
        ]
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            with patch.object(ev, "_run_single_test", side_effect=results):
                report = ev.evaluate(tmp_path / "skill")
        assert "explicit" in report.summary_by_type
        assert "implicit" in report.summary_by_type

    def test_evaluate_accepts_string_path(self, tmp_path: Path):
        skill_path = str(tmp_path / "skill")
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=([], [])):
            report = ev.evaluate(skill_path)
        assert isinstance(report, TriggerReport)

    def test_evaluate_duration_ms_positive(self, tmp_path: Path):
        tc = _make_test_case()
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=([tc], [])):
            with patch.object(ev, "_run_single_test", return_value=_make_trigger_result()):
                report = ev.evaluate(tmp_path / "skill")
        assert report.duration_ms >= 0

    def test_evaluate_timestamp_is_iso_string(self, tmp_path: Path):
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=([], [])):
            report = ev.evaluate(tmp_path / "skill")
        # Basic check: it's a non-empty ISO-like string
        assert "T" in report.timestamp
        assert "Z" in report.timestamp or "+" in report.timestamp

    def test_report_includes_provider_name(self, tmp_path: Path):
        ev = self._evaluator_with_runtime()
        with patch(self._PATCH_LOAD, return_value=([], [])):
            report = ev.evaluate(tmp_path / "skill")
        assert report.provider == "local"


# ─── _get_provider ───────────────────────────────────────────────────────────


class TestGetProvider:
    def test_default_provider_is_local(self):
        evaluator = TriggerEvaluator()
        provider = evaluator._get_provider()
        assert isinstance(provider, LocalProvider)
        assert provider.name == "local"

    def test_explicit_local_provider(self):
        evaluator = TriggerEvaluator(provider="local")
        provider = evaluator._get_provider()
        assert isinstance(provider, LocalProvider)

    def test_docker_provider_raises_not_implemented(self):
        from skill_lab.core.exceptions import ProviderError

        evaluator = TriggerEvaluator(provider="docker")
        with pytest.raises(ProviderError, match="not yet implemented"):
            evaluator._get_provider()

    def test_unknown_provider_raises_error(self):
        from skill_lab.core.exceptions import ProviderError

        evaluator = TriggerEvaluator(provider="foobar")
        with pytest.raises(ProviderError, match="Unknown provider"):
            evaluator._get_provider()


# ─── Provider lifecycle in evaluate() ────────────────────────────────────────


class TestProviderLifecycle:
    _PATCH_LOAD = "skill_lab.triggers.trigger_evaluator.load_trigger_tests"

    def test_setup_and_teardown_called(self, tmp_path: Path):
        provider = FakeProvider()
        ev = TriggerEvaluator()
        ev._get_runtime = lambda: FakeRuntime()  # type: ignore[method-assign]
        ev._get_provider = lambda: provider  # type: ignore[method-assign]

        with patch(self._PATCH_LOAD, return_value=([], [])):
            ev.evaluate(tmp_path / "skill")

        assert provider.setup_called
        assert provider.teardown_called

    def test_teardown_called_on_test_error(self, tmp_path: Path):
        """teardown() runs even if a test raises."""
        provider = FakeProvider()
        ev = TriggerEvaluator()
        ev._get_runtime = lambda: FakeRuntime()  # type: ignore[method-assign]
        ev._get_provider = lambda: provider  # type: ignore[method-assign]

        tc = _make_test_case()
        with patch(self._PATCH_LOAD, return_value=([tc], [])):
            with patch.object(
                ev,
                "_run_single_test",
                side_effect=RuntimeError("boom"),
            ):
                with pytest.raises(RuntimeError):
                    ev.evaluate(tmp_path / "skill")

        assert provider.teardown_called

    def test_prepare_and_cleanup_called_per_test(self, tmp_path: Path):
        provider = FakeProvider()
        ev = TriggerEvaluator()
        runtime = FakeRuntime()
        ev._get_runtime = lambda: runtime  # type: ignore[method-assign]
        ev._get_provider = lambda: provider  # type: ignore[method-assign]

        tcs = [_make_test_case(id=f"t{i}", skill_triggered=False) for i in range(3)]
        with patch(self._PATCH_LOAD, return_value=(tcs, [])):
            ev.evaluate(tmp_path / "skill")

        assert provider.prepare_count == 3
        assert provider.cleanup_count == 3
