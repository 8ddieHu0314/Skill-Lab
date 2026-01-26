"""Quality score calculation for evaluation results."""

from agent_skills_eval.core.models import CheckResult, EvalDimension, Severity

# Weights for each dimension in the final score
DIMENSION_WEIGHTS: dict[EvalDimension, float] = {
    EvalDimension.STRUCTURE: 0.30,
    EvalDimension.NAMING: 0.20,
    EvalDimension.DESCRIPTION: 0.25,
    EvalDimension.CONTENT: 0.25,
}

# Weights for severity levels when calculating dimension scores
SEVERITY_WEIGHTS: dict[Severity, float] = {
    Severity.ERROR: 1.0,
    Severity.WARNING: 0.5,
    Severity.INFO: 0.25,
}


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


def build_summary(results: list[CheckResult]) -> dict:
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
