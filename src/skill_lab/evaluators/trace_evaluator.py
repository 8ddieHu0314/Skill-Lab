"""Trace evaluator for running trace checks against execution traces."""

import time
from datetime import datetime, timezone
from pathlib import Path

from skill_lab.core.models import TraceCheckResult, TraceReport
from skill_lab.core.scoring import build_summary_by_attribute, calculate_metrics
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

# Side-effect references: These handlers are imported above but the references below
# ensure they are not removed by linters/dead-code analyzers. The @register_trace_handler
# decorator on each class registers it with trace_registry when the module is imported.
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
        metrics = calculate_metrics(results)
        overall_pass = metrics.failed == 0

        # Build summary
        summary = {"by_type": build_summary_by_attribute(results, "check_type")}

        return TraceReport(
            trace_path=str(trace_path),
            project_dir=str(skill_path),
            timestamp=timestamp,
            duration_ms=duration_ms,
            checks_run=metrics.total,
            checks_passed=metrics.passed,
            checks_failed=metrics.failed,
            overall_pass=overall_pass,
            pass_rate=metrics.pass_rate,
            results=results,
            summary=summary,
        )
