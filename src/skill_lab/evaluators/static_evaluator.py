"""Static evaluator for running all static checks on a skill."""

import time
from datetime import datetime, timezone
from pathlib import Path

from skill_lab.checks.base import StaticCheck

# Side-effect imports: importing these modules triggers @register_check decorators,
# which register all check classes with the global CheckRegistry singleton.
# The imports appear unused but are required for the auto-discovery pattern.
from skill_lab.checks.static import (  # noqa: F401
    content,
    description,
    frontmatter,
    naming,
    structure,
)
from skill_lab.core.models import CheckResult, EvaluationReport, Severity
from skill_lab.core.registry import registry
from skill_lab.core.scoring import build_summary, calculate_metrics, calculate_score
from skill_lab.parsers.skill_parser import parse_skill


class StaticEvaluator:
    """Evaluator that runs static checks on skills."""

    def __init__(
        self,
        check_ids: list[str] | None = None,
        spec_only: bool = False,
    ) -> None:
        """Initialize the evaluator.

        Args:
            check_ids: Optional list of specific check IDs to run.
                      If None, all registered checks are run.
            spec_only: If True, only run checks required by the Agent Skills spec.
                      Quality suggestion checks will be skipped.
        """
        self.check_ids = check_ids
        self.spec_only = spec_only

    def _get_checks(self) -> list[StaticCheck]:
        """Get the check instances to run.

        Returns:
            List of check instances.
        """
        if self.check_ids:
            checks = []
            for check_id in self.check_ids:
                check_class = registry.get(check_id)
                if check_class:
                    # If spec_only, skip non-spec-required checks
                    if self.spec_only and not check_class.spec_required:
                        continue
                    checks.append(check_class())
            return checks
        elif self.spec_only:
            return [check_class() for check_class in registry.get_spec_required()]
        else:
            return [check_class() for check_class in registry.get_all()]

    def evaluate(self, skill_path: str | Path) -> EvaluationReport:
        """Evaluate a skill at the given path.

        Args:
            skill_path: Path to the skill directory.

        Returns:
            EvaluationReport with all check results.
        """
        start_time = time.perf_counter()

        # Parse the skill
        skill = parse_skill(skill_path)

        # Run all checks
        results: list[CheckResult] = []
        checks = self._get_checks()

        for check in checks:
            try:
                result = check.run(skill)
                results.append(result)
            except Exception as e:
                # If a check fails unexpectedly, record it as a failed check
                results.append(
                    CheckResult(
                        check_id=check.check_id,
                        check_name=check.check_name,
                        passed=False,
                        severity=check.severity,
                        dimension=check.dimension,
                        message=f"Check failed with error: {e}",
                        details={"error": str(e)},
                    )
                )

        # Calculate metrics
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000

        metrics = calculate_metrics(results)

        # Determine overall pass (no ERROR-level failures)
        error_failures = [
            r for r in results if not r.passed and r.severity == Severity.ERROR
        ]
        overall_pass = len(error_failures) == 0

        # Calculate quality score
        quality_score = calculate_score(results)

        # Build summary
        summary = build_summary(results)

        return EvaluationReport(
            skill_path=str(skill.path),
            skill_name=skill.metadata.name if skill.metadata else None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=round(duration_ms, 2),
            quality_score=quality_score,
            overall_pass=overall_pass,
            checks_run=metrics.total,
            checks_passed=metrics.passed,
            checks_failed=metrics.failed,
            results=results,
            summary=summary,
        )

    def validate(self, skill_path: str | Path) -> tuple[bool, list[CheckResult]]:
        """Quick validation that returns only ERROR-level failures.

        Args:
            skill_path: Path to the skill directory.

        Returns:
            Tuple of (passed, error_results).
        """
        report = self.evaluate(skill_path)
        error_results = [
            r for r in report.results if not r.passed and r.severity == Severity.ERROR
        ]
        return report.overall_pass, error_results
