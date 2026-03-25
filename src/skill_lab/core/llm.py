"""Shared LLM types, provider abstraction, and pricing for generator/optimizer modules.

Supports three providers (Anthropic, OpenAI, Google Gemini) via a unified interface.
Provider is auto-detected from the model ID prefix. API keys are read from standard
environment variables (ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Pricing per million tokens (input, output) — updated 2026-03
_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (5.00, 25.00),
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o3-mini": (1.10, 4.40),
    # Google Gemini
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 3.50),
    "gemini-2.0-flash": (0.10, 0.40),
}

# Provider name constants
ANTHROPIC = "anthropic"
OPENAI = "openai"
GEMINI = "gemini"

# Model prefix → provider mapping
_OPENAI_PREFIXES = ("gpt-", "o1-", "o3-", "o4-")
_GEMINI_PREFIXES = ("gemini-",)

# Env var per provider
_API_KEY_ENV_VARS: dict[str, str] = {
    ANTHROPIC: "ANTHROPIC_API_KEY",
    OPENAI: "OPENAI_API_KEY",
    GEMINI: "GEMINI_API_KEY",
}


class GenerationUsage:
    """Token usage and cost from a generation API call."""

    def __init__(self, input_tokens: int, output_tokens: int, model: str) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def input_cost(self) -> float:
        """Input cost in USD. Returns 0.0 for unknown models."""
        pricing = _PRICING.get(self.model)
        if pricing is None:
            return 0.0
        return self.input_tokens * pricing[0] / 1_000_000

    @property
    def output_cost(self) -> float:
        """Output cost in USD. Returns 0.0 for unknown models."""
        pricing = _PRICING.get(self.model)
        if pricing is None:
            return 0.0
        return self.output_tokens * pricing[1] / 1_000_000

    @property
    def total_cost(self) -> float:
        """Total cost in USD."""
        return self.input_cost + self.output_cost

    @property
    def has_pricing(self) -> bool:
        """Whether pricing data is available for this model."""
        return self.model in _PRICING


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response from any LLM provider."""

    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str  # "end_turn" | "max_tokens" | "stop"


class LLMProvider(Protocol):
    """Protocol for LLM provider implementations."""

    def create_message(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        prompt: str,
    ) -> LLMResponse: ...


class AnthropicProvider:
    """LLM provider using the Anthropic SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)

    def create_message(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        prompt: str,
    ) -> LLMResponse:
        message = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts = [block.text for block in message.content if hasattr(block, "text")]
        return LLMResponse(
            text="\n".join(text_parts),
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            stop_reason=message.stop_reason or "end_turn",
        )


class OpenAIProvider:
    """LLM provider using the OpenAI SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key)

    def create_message(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        prompt: str,
    ) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        choice = response.choices[0]
        text = choice.message.content or ""
        usage = response.usage
        return LLMResponse(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            stop_reason="max_tokens" if choice.finish_reason == "length" else "end_turn",
        )


class GeminiProvider:
    """LLM provider using the Google Generative AI SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        import google.generativeai as genai

        self._genai: Any = genai
        # NOTE: genai.configure() sets the API key at module level (global state).
        # Multiple GeminiProvider instances with different keys would conflict.
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._genai.configure(api_key=resolved_key)

    def create_message(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        prompt: str,
    ) -> LLMResponse:
        gen_model = self._genai.GenerativeModel(
            model_name=model,
            system_instruction=system,
            generation_config=self._genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0,
            ),
        )
        response = gen_model.generate_content(prompt)

        safety_blocked = False
        try:
            text: str = response.text or ""
        except ValueError:
            # Gemini raises ValueError when response is blocked by safety filters
            text = ""
            safety_blocked = True
        usage_metadata = response.usage_metadata
        input_tokens: int = getattr(usage_metadata, "prompt_token_count", 0) or 0
        output_tokens: int = getattr(usage_metadata, "candidates_token_count", 0) or 0

        finish_reason = ""
        if response.candidates:
            finish_reason = str(getattr(response.candidates[0], "finish_reason", ""))

        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=(
                "safety"
                if safety_blocked
                else "max_tokens"
                if "MAX_TOKENS" in finish_reason
                else "end_turn"
            ),
        )


def detect_provider_name(model: str) -> str:
    """Detect which provider a model belongs to based on its ID prefix.

    Returns:
        Provider name: "anthropic", "openai", or "gemini".
    """
    if model.startswith(_OPENAI_PREFIXES):
        return OPENAI
    if model.startswith(_GEMINI_PREFIXES):
        return GEMINI
    return ANTHROPIC


def get_api_key_env_var(provider_name: str) -> str:
    """Get the environment variable name for a provider's API key."""
    return _API_KEY_ENV_VARS.get(provider_name, "ANTHROPIC_API_KEY")


def resolve_provider(model: str, api_key: str | None = None) -> LLMProvider:
    """Create the appropriate LLMProvider for a given model.

    Args:
        model: Model ID (used to detect provider).
        api_key: Optional API key override. If None, uses env var.

    Returns:
        An LLMProvider instance for the detected provider.
    """
    provider_name = detect_provider_name(model)
    if provider_name == OPENAI:
        return OpenAIProvider(api_key=api_key)
    if provider_name == GEMINI:
        return GeminiProvider(api_key=api_key)
    return AnthropicProvider(api_key=api_key)
