"""Shared LLM types and constants used across generator and optimizer modules."""

from __future__ import annotations

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Pricing per million tokens (input, output) — updated 2026-03
_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (5.00, 25.00),
}


class GenerationUsage:
    """Token usage and cost from a generation API call."""

    def __init__(self, input_tokens: int, output_tokens: int, model: str) -> None:
        if model not in _PRICING:
            raise ValueError(f"Unknown model '{model}' — add it to skill_lab.core.llm._PRICING")
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def input_cost(self) -> float:
        """Input cost in USD."""
        pricing = _PRICING[self.model]
        return self.input_tokens * pricing[0] / 1_000_000

    @property
    def output_cost(self) -> float:
        """Output cost in USD."""
        pricing = _PRICING[self.model]
        return self.output_tokens * pricing[1] / 1_000_000

    @property
    def total_cost(self) -> float:
        """Total cost in USD."""
        return self.input_cost + self.output_cost
