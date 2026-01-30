"""Orchestrate trigger test execution."""

import time
from datetime import datetime, timezone
from pathlib import Path

from skill_lab.core.models import (
    TriggerReport,
    TriggerResult,
    TriggerTestCase,
    TriggerType,
)
from skill_lab.core.scoring import build_summary_by_attribute, calculate_metrics
from skill_lab.runtimes.base import RuntimeAdapter
from skill_lab.runtimes.claude_runtime import ClaudeRuntime
from skill_lab.runtimes.codex_runtime import CodexRuntime
from skill_lab.triggers.test_loader import load_trigger_tests
from skill_lab.triggers.trace_analyzer import TraceAnalyzer


class TriggerEvaluator:
    """Orchestrate trigger testing for skills.

    The evaluator:
    1. Loads test cases from YAML
    2. Executes each test through the selected runtime
    3. Analyzes traces for skill invocations
    4. Produces a TriggerReport with pass rates by trigger type
    """

    def __init__(
        self,
        runtime: str | None = None,
        trace_dir: Path | None = None,
    ) -> None:
        """Initialize the trigger evaluator.

        Args:
            runtime: Runtime to use ('codex', 'claude', or None for auto-detect).
            trace_dir: Directory to store execution traces.
        """
        self._runtime_name = runtime
        self._trace_dir = trace_dir or Path(".skill-lab/traces")

    def evaluate(
        self,
        skill_path: Path | str,
        type_filter: TriggerType | None = None,
    ) -> TriggerReport:
        """Run trigger tests for a skill.

        Args:
            skill_path: Path to the skill directory.
            type_filter: Optional filter to run only tests of a specific type.

        Returns:
            TriggerReport with all test results.
        """
        start_time = time.time()
        skill_path = Path(skill_path)

        # Load test cases
        test_cases, load_errors = load_trigger_tests(skill_path)

        # Filter by type if requested
        if type_filter:
            test_cases = [tc for tc in test_cases if tc.trigger_type == type_filter]

        # Get runtime adapter
        runtime = self._get_runtime()

        # Extract skill name
        skill_name = self._get_skill_name(skill_path, test_cases)

        # Run tests
        results: list[TriggerResult] = []

        if load_errors and not test_cases:
            # No tests to run, report loading errors
            for error in load_errors:
                results.append(
                    TriggerResult(
                        test_id="load-error",
                        test_name="Test Loading",
                        trigger_type=TriggerType.EXPLICIT,
                        passed=False,
                        skill_triggered=False,
                        expected_trigger=True,
                        message=error,
                    )
                )
        else:
            for test_case in test_cases:
                result = self._run_single_test(test_case, skill_path, runtime)
                results.append(result)

        # Calculate metrics
        duration_ms = (time.time() - start_time) * 1000
        metrics = calculate_metrics(results)

        # Build summary by trigger type
        summary_by_type = build_summary_by_attribute(results, "trigger_type")

        return TriggerReport(
            skill_path=str(skill_path),
            skill_name=skill_name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            runtime=runtime.name,
            tests_run=metrics.total,
            tests_passed=metrics.passed,
            tests_failed=metrics.failed,
            overall_pass=metrics.failed == 0,
            pass_rate=metrics.pass_rate / 100 if results else 0.0,  # Convert to 0-1 range
            results=results,
            summary_by_type=summary_by_type,
        )

    def _get_runtime(self) -> RuntimeAdapter:
        """Get the runtime adapter to use."""
        if self._runtime_name == "codex":
            return CodexRuntime()
        elif self._runtime_name == "claude":
            return ClaudeRuntime()
        else:
            # Auto-detect: prefer codex if available
            codex = CodexRuntime()
            if codex.is_available():
                return codex
            claude = ClaudeRuntime()
            if claude.is_available():
                return claude
            # Default to codex even if not available (will fail with helpful error)
            return codex

    def _get_skill_name(
        self, skill_path: Path, test_cases: list[TriggerTestCase]
    ) -> str:
        """Extract skill name from test cases or path."""
        for tc in test_cases:
            if tc.skill_name and tc.skill_name != "unknown":
                return tc.skill_name
        return skill_path.name

    def _run_single_test(
        self,
        test_case: TriggerTestCase,
        skill_path: Path,
        runtime: RuntimeAdapter,
    ) -> TriggerResult:
        """Execute a single trigger test.

        Args:
            test_case: The test case to run.
            skill_path: Path to the skill directory.
            runtime: Runtime adapter to use.

        Returns:
            TriggerResult for this test.
        """
        # Determine trace path
        trace_path = self._trace_dir / f"{test_case.id}.jsonl"
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Execute the prompt
            exit_code = runtime.execute(
                prompt=test_case.prompt,
                skill_path=skill_path,
                trace_path=trace_path,
            )

            # Parse and analyze the trace
            events = list(runtime.parse_trace(trace_path))
            analyzer = TraceAnalyzer(events)

            # Check if skill was triggered
            skill_triggered = analyzer.skill_was_triggered(test_case.skill_name)

            # Check expectations
            passed = self._check_expectations(
                test_case, analyzer, skill_path, skill_triggered, exit_code
            )

            # Build message
            if passed:
                message = f"Test passed: {test_case.name}"
            else:
                expected_str = "trigger" if test_case.expected.skill_triggered else "no trigger"
                actual_str = "triggered" if skill_triggered else "not triggered"
                message = f"Expected {expected_str}, but skill was {actual_str}"

            return TriggerResult(
                test_id=test_case.id,
                test_name=test_case.name,
                trigger_type=test_case.trigger_type,
                passed=passed,
                skill_triggered=skill_triggered,
                expected_trigger=test_case.expected.skill_triggered,
                message=message,
                trace_path=trace_path,
                events_count=len(events),
                exit_code=exit_code,
            )

        except Exception as e:
            return TriggerResult(
                test_id=test_case.id,
                test_name=test_case.name,
                trigger_type=test_case.trigger_type,
                passed=False,
                skill_triggered=False,
                expected_trigger=test_case.expected.skill_triggered,
                message=f"Test execution failed: {e}",
                trace_path=trace_path,
                details={"error": str(e)},
            )

    def _check_expectations(
        self,
        test_case: TriggerTestCase,
        analyzer: TraceAnalyzer,
        skill_path: Path,
        skill_triggered: bool,
        exit_code: int,
    ) -> bool:
        """Check if all expectations are met.

        Args:
            test_case: The test case with expectations.
            analyzer: Trace analyzer with parsed events.
            skill_path: Path to skill directory.
            skill_triggered: Whether the skill was triggered.
            exit_code: Exit code from runtime.

        Returns:
            True if all expectations are met.
        """
        expected = test_case.expected

        # Check skill trigger expectation
        if skill_triggered != expected.skill_triggered:
            return False

        # Check exit code if specified
        if expected.exit_code is not None and exit_code != expected.exit_code:
            return False

        # Check required commands
        for cmd in expected.commands_include:
            if not analyzer.command_was_run(cmd):
                return False

        # Check file creation
        for filepath in expected.files_created:
            if not analyzer.file_was_created(filepath, skill_path):
                return False

        # Check for loops
        return not (expected.no_loops and analyzer.detect_loops())

