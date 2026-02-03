"""Orchestrate trigger test execution."""

import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from skill_lab.core.models import (
    Skill,
    TriggerReport,
    TriggerResult,
    TriggerTestCase,
    TriggerType,
)
from skill_lab.core.scoring import build_summary_by_attribute, calculate_metrics
from skill_lab.parsers.skill_parser import parse_skill
from skill_lab.runtimes.base import RuntimeAdapter
from skill_lab.runtimes.claude_runtime import ClaudeRuntime
from skill_lab.runtimes.codex_runtime import CodexRuntime
from skill_lab.triggers.failure_analyzer import FailureAnalyzer
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
        analyze_failures: bool = True,
    ) -> None:
        """Initialize the trigger evaluator.

        Args:
            runtime: Runtime to use ('codex', 'claude', or None for auto-detect).
            trace_dir: Directory to store execution traces.
            analyze_failures: Whether to analyze failures and generate suggestions.
        """
        self._runtime_name = runtime
        self._trace_dir = trace_dir or Path(".skill-lab/traces")
        self._analyze_failures = analyze_failures
        self._failure_analyzer = FailureAnalyzer() if analyze_failures else None

    def _find_project_root(self, skill_path: Path) -> Path | None:
        """Find the project root directory containing .claude/skills/.

        Traverses up from skill_path to find a directory that contains
        .claude/skills/. This is used to run implicit tests from a location
        where Claude can discover project-level skills.

        Args:
            skill_path: Path to the skill directory.

        Returns:
            Path to project root, or None if not found.
        """
        # skill_path is typically: /project/.claude/skills/skill-name
        # We want to find: /project (which contains .claude/skills/)
        current = skill_path.resolve()

        # Traverse up to find .claude/skills/
        for _ in range(10):  # Limit depth to avoid infinite loop
            # Check if this directory contains .claude/skills/
            if (current / ".claude" / "skills").is_dir():
                return current

            # Check if we're inside .claude/skills/ already
            if current.name == "skills" and current.parent.name == ".claude":
                return current.parent.parent

            parent = current.parent
            if parent == current:  # Reached root
                break
            current = parent

        return None

    def evaluate(
        self,
        skill_path: Path | str,
        type_filter: TriggerType | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> TriggerReport:
        """Run trigger tests for a skill.

        Args:
            skill_path: Path to the skill directory.
            type_filter: Optional filter to run only tests of a specific type.
            progress_callback: Optional callback(current, total, test_name) for progress updates.

        Returns:
            TriggerReport with all test results.
        """
        start_time = time.time()
        skill_path = Path(skill_path)

        # Find project root for implicit tests (where .claude/skills/ is visible)
        project_root = self._find_project_root(skill_path)

        # Load test cases
        test_cases, load_errors = load_trigger_tests(skill_path)

        # Filter by type if requested
        if type_filter:
            test_cases = [tc for tc in test_cases if tc.trigger_type == type_filter]

        # Get runtime adapter
        runtime = self._get_runtime()

        # Extract skill name
        skill_name = self._get_skill_name(skill_path, test_cases)

        # Parse skill for failure analysis (if enabled)
        skill: Skill | None = None
        if self._analyze_failures:
            skill = parse_skill(skill_path)

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
            total = len(test_cases)
            for i, test_case in enumerate(test_cases):
                if progress_callback:
                    progress_callback(i + 1, total, test_case.name)
                result = self._run_single_test(test_case, skill_path, runtime, project_root)

                # Analyze failure if enabled and test failed
                if not result.passed and self._failure_analyzer and skill:
                    analysis = self._failure_analyzer.analyze(test_case, result, skill)
                    if analysis:
                        # Create new result with analysis attached
                        result = TriggerResult(
                            test_id=result.test_id,
                            test_name=result.test_name,
                            trigger_type=result.trigger_type,
                            passed=result.passed,
                            skill_triggered=result.skill_triggered,
                            expected_trigger=result.expected_trigger,
                            message=result.message,
                            trace_path=result.trace_path,
                            events_count=result.events_count,
                            exit_code=result.exit_code,
                            details=result.details,
                            failure_analysis=analysis,
                        )

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
        project_root: Path | None = None,
    ) -> TriggerResult:
        """Execute a single trigger test.

        Args:
            test_case: The test case to run.
            skill_path: Path to the skill directory.
            runtime: Runtime adapter to use.
            project_root: Project root directory (where .claude/skills/ exists).
                Used for implicit/contextual tests to test skill discovery.

        Returns:
            TriggerResult for this test.
        """
        # Determine trace path
        trace_path = self._trace_dir / f"{test_case.id}.jsonl"
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine working directory based on trigger type:
        # - Explicit tests: Run from skill_path (CLI expands $skill-name)
        # - Implicit/contextual/negative: Run from project_root (Claude discovers skill)
        if test_case.trigger_type == TriggerType.EXPLICIT:
            working_dir = skill_path
        else:
            working_dir = project_root if project_root else skill_path

        try:
            # For positive tests (expecting trigger), enable early termination
            # to save time and cost once the skill is detected
            stop_on_skill = None
            if test_case.expected.skill_triggered:
                stop_on_skill = test_case.skill_name

            # Execute the prompt
            exit_code = runtime.execute(
                prompt=test_case.prompt,
                skill_path=skill_path,
                trace_path=trace_path,
                stop_on_skill=stop_on_skill,
                working_dir=working_dir,
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

