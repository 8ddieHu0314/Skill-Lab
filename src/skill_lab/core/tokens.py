"""Token estimation utilities for skill cost analysis."""


def estimate_tokens(text: str) -> int:
    """Estimate token count using chars/4 heuristic.

    This is an approximation suitable for authoring guidance.
    No external dependency (no tiktoken) required.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count (minimum 0).
    """
    return max(0, len(text) // 4)
