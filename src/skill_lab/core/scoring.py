"""Quality score calculation for evaluation results."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from skill_lab.core.models import CheckResult, EvalDimension, Severity

# Weights for each dimension in the final score
# Note: EXECUTION dimension is for trace-based checks and has 0 weight
# in static analysis scoring. It's evaluated separately via trace evaluation.
DIMENSION_WEIGHTS: dict[EvalDimension, float] = {
    EvalDimension.STRUCTURE: 0.30,
    EvalDimension.NAMING: 0.20,
    EvalDimension.DESCRIPTION: 0.25,
    EvalDimension.CONTENT: 0.25,
    EvalDimension.EXECUTION: 0.0,  # Evaluated separately via trace evaluation
}

# Weights for severity levels when calculating dimension scores
SEVERITY_WEIGHTS: dict[Severity, float] = {
    Severity.ERROR: 1.0,
    Severity.WARNING: 0.5,
    Severity.INFO: 0.25,
}


# Protocol for results that have a 'passed' attribute
class HasPassed(Protocol):
    """Protocol for objects with a passed attribute."""

    @property
    def passed(self) -> bool: ...


T = TypeVar("T", bound=HasPassed)


@dataclass
class EvaluationMetrics:
    """Common metrics calculated from evaluation results."""

    total: int
    passed: int
    failed: int
    pass_rate: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
        }


def calculate_metrics(results: list[T]) -> EvaluationMetrics:
    """Calculate common metrics from any list of results with 'passed' attribute.

    This utility function is used by all evaluators to compute consistent metrics.

    Args:
        results: List of result objects with a 'passed' attribute.

    Returns:
        EvaluationMetrics with passed/failed counts and pass rate.
    """
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    return EvaluationMetrics(
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
    )


def calculate_dimension_score(results: list[CheckResult]) -> float:
    """Calculate the score for a single dimension based on its check results.

    Args:
        results: List of check results for a single dimension.

    Returns:
        Score from 0-100 for the dimension.
    """
    if not results:
        return 100.0

    total_weight = sum(SEVERITY_WEIGHTS[r.severity] for r in results)
    passed_weight = sum(SEVERITY_WEIGHTS[r.severity] for r in results if r.passed)

    if total_weight == 0:
        return 100.0

    return (passed_weight / total_weight) * 100


def calculate_score(results: list[CheckResult]) -> float:
    """Calculate the composite quality score from check results.

    Args:
        results: List of all check results.

    Returns:
        Quality score from 0-100.
    """
    dimension_scores: dict[EvalDimension, float] = {}

    for dim in EvalDimension:
        dim_results = [r for r in results if r.dimension == dim]
        dimension_scores[dim] = calculate_dimension_score(dim_results)

    # Calculate weighted average
    total_score = sum(
        dimension_scores[dim] * DIMENSION_WEIGHTS[dim] for dim in EvalDimension
    )

    return round(total_score, 2)


def build_summary(results: list[CheckResult]) -> dict[str, Any]:
    """Build a summary of results by severity and dimension.

    Args:
        results: List of all check results.

    Returns:
        Summary dictionary with breakdowns by severity and dimension.
    """
    by_severity: dict[str, dict[str, int]] = {}
    by_dimension: dict[str, dict[str, int]] = {}

    # Initialize counters
    for severity in Severity:
        by_severity[severity.value] = {"passed": 0, "failed": 0}
    for dim in EvalDimension:
        by_dimension[dim.value] = {"passed": 0, "failed": 0}

    # Count results
    for result in results:
        severity_key = result.severity.value
        dimension_key = result.dimension.value

        if result.passed:
            by_severity[severity_key]["passed"] += 1
            by_dimension[dimension_key]["passed"] += 1
        else:
            by_severity[severity_key]["failed"] += 1
            by_dimension[dimension_key]["failed"] += 1

    return {
        "by_severity": by_severity,
        "by_dimension": by_dimension,
    }


def build_summary_by_attribute(
    results: list[T],
    attribute: str,
    value_extractor: Callable[[Any], str] | None = None,
) -> dict[str, dict[str, int]]:
    """Build a summary of results grouped by an attribute.

    Generic utility for building summaries grouped by any attribute
    (e.g., check_type, trigger_type).

    Args:
        results: List of result objects.
        attribute: Name of the attribute to group by.
        value_extractor: Optional function to extract the grouping value.
                        If None, uses getattr with .value for enums.

    Returns:
        Dictionary mapping attribute values to pass/fail/total counts.
    """
    summary: dict[str, dict[str, int]] = {}

    for result in results:
        # Get the attribute value
        attr_value = getattr(result, attribute)
        if value_extractor:
            key = value_extractor(attr_value)
        elif hasattr(attr_value, "value"):
            key = attr_value.value
        else:
            key = str(attr_value)

        # Initialize if needed
        if key not in summary:
            summary[key] = {"total": 0, "passed": 0, "failed": 0}

        # Update counts
        summary[key]["total"] += 1
        if result.passed:
            summary[key]["passed"] += 1
        else:
            summary[key]["failed"] += 1

    return summary
