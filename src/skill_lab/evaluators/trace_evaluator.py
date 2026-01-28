"""Trace evaluator for running trace checks against execution traces."""

import time
from datetime import datetime, timezone
from pathlib import Path

from skill_lab.core.models import TraceCheckResult, TraceReport
from skill_lab.parsers.trace_parser import parse_trace_file
from skill_lab.tracechecks.handlers import (
    CommandPresenceHandler,
    EfficiencyHandler,
    EventSequenceHandler,
    FileCreationHandler,
    LoopDetectionHandler,
)
from skill_lab.tracechecks.registry import trace_registry
from skill_lab.tracechecks.trace_check_loader import load_trace_checks
from skill_lab.triggers.trace_analyzer import TraceAnalyzer

# Ensure handlers are registered by importing them
_ = (
    CommandPresenceHandler,
    FileCreationHandler,
    EventSequenceHandler,
    LoopDetectionHandler,
    EfficiencyHandler,
)


class TraceEvaluator:
    """Evaluator for running YAML-defined trace checks.

    Loads check definitions from tests/trace_checks.yaml, parses the
    trace file, and runs each check using the appropriate handler.
    """

    def __init__(self) -> None:
        """Initialize the trace evaluator."""
        pass

    def evaluate(self, skill_path: Path, trace_path: Path) -> TraceReport:
        """Evaluate a trace against the skill's trace checks.

        Args:
            skill_path: Path to the skill directory (contains tests/trace_checks.yaml).
            trace_path: Path to the JSONL trace file.

        Returns:
            TraceReport with all check results.

        Raises:
            FileNotFoundError: If trace_checks.yaml or trace file doesn't exist.
            ValueError: If YAML is malformed or a handler is missing.
        """
        start_time = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat()

        # Load check definitions
        checks = load_trace_checks(skill_path)

        # Parse trace file
        events = parse_trace_file(trace_path)
        analyzer = TraceAnalyzer(events)

        # Run checks
        results: list[TraceCheckResult] = []
        for check in checks:
            handler_class = trace_registry.get(check.type)
            if handler_class is None:
                # Create a failing result for unknown check type
                results.append(
                    TraceCheckResult(
                        check_id=check.id,
                        check_type=check.type,
                        passed=False,
                        message=f"Unknown check type: {check.type}",
                    )
                )
                continue

            try:
                handler = handler_class()
                result = handler.run(check, analyzer, skill_path)
                results.append(result)
            except Exception as e:
                results.append(
                    TraceCheckResult(
                        check_id=check.id,
                        check_type=check.type,
                        passed=False,
                        message=f"Check error: {e}",
                        details={"error_type": type(e).__name__},
                    )
                )

        # Calculate metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        checks_passed = sum(1 for r in results if r.passed)
        checks_failed = len(results) - checks_passed
        pass_rate = (checks_passed / len(results) * 100) if results else 0.0
        overall_pass = checks_failed == 0

        # Build summary
        summary = self._build_summary(results)

        return TraceReport(
            trace_path=str(trace_path),
            project_dir=str(skill_path),
            timestamp=timestamp,
            duration_ms=duration_ms,
            checks_run=len(results),
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            overall_pass=overall_pass,
            pass_rate=pass_rate,
            results=results,
            summary=summary,
        )

    def _build_summary(self, results: list[TraceCheckResult]) -> dict[str, object]:
        """Build a summary of results by check type.

        Args:
            results: List of check results.

        Returns:
            Summary dictionary with breakdown by type.
        """
        by_type: dict[str, dict[str, int]] = {}

        for result in results:
            if result.check_type not in by_type:
                by_type[result.check_type] = {"passed": 0, "failed": 0, "total": 0}

            by_type[result.check_type]["total"] += 1
            if result.passed:
                by_type[result.check_type]["passed"] += 1
            else:
                by_type[result.check_type]["failed"] += 1

        return {"by_type": by_type}
