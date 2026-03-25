"""Unit tests for LLM provider abstraction, pricing, and detection logic."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from skill_lab.core.llm import (
    ANTHROPIC,
    GEMINI,
    OPENAI,
    AnthropicProvider,
    GeminiProvider,
    GenerationUsage,
    LLMResponse,
    OpenAIProvider,
    detect_provider_name,
    get_api_key_env_var,
    resolve_provider,
)


class TestDetectProviderName:
    """Tests for model ID → provider detection."""

    @pytest.mark.parametrize(
        "model,expected",
        [
            # Anthropic models
            ("claude-haiku-4-5-20251001", ANTHROPIC),
            ("claude-sonnet-4-6", ANTHROPIC),
            ("claude-opus-4-6", ANTHROPIC),
            ("claude-sonnet-4-5-20250929", ANTHROPIC),
            # OpenAI models
            ("gpt-4o", OPENAI),
            ("gpt-4o-mini", OPENAI),
            ("gpt-4.1", OPENAI),
            ("gpt-4.1-mini", OPENAI),
            ("gpt-4.1-nano", OPENAI),
            ("o3-mini", OPENAI),
            ("o1-preview", OPENAI),
            ("o4-mini", OPENAI),
            # Gemini models
            ("gemini-2.5-pro", GEMINI),
            ("gemini-2.5-flash", GEMINI),
            ("gemini-2.0-flash", GEMINI),
            # Unknown → defaults to Anthropic
            ("some-custom-model", ANTHROPIC),
        ],
    )
    def test_detection(self, model: str, expected: str) -> None:
        assert detect_provider_name(model) == expected


class TestGetApiKeyEnvVar:
    """Tests for provider → env var mapping."""

    def test_anthropic(self) -> None:
        assert get_api_key_env_var(ANTHROPIC) == "ANTHROPIC_API_KEY"

    def test_openai(self) -> None:
        assert get_api_key_env_var(OPENAI) == "OPENAI_API_KEY"

    def test_gemini(self) -> None:
        assert get_api_key_env_var(GEMINI) == "GEMINI_API_KEY"

    def test_unknown_falls_back_to_anthropic(self) -> None:
        assert get_api_key_env_var("unknown") == "ANTHROPIC_API_KEY"


class TestGenerationUsage:
    """Tests for GenerationUsage cost calculations."""

    def test_anthropic_model_cost(self) -> None:
        usage = GenerationUsage(
            input_tokens=1000, output_tokens=500, model="claude-haiku-4-5-20251001"
        )
        assert usage.total_tokens == 1500
        assert usage.has_pricing is True
        assert usage.input_cost == pytest.approx(0.001)
        assert usage.output_cost == pytest.approx(0.0025)
        assert usage.total_cost == pytest.approx(0.0035)

    def test_openai_model_cost(self) -> None:
        usage = GenerationUsage(input_tokens=1000, output_tokens=500, model="gpt-4o")
        assert usage.has_pricing is True
        assert usage.input_cost == pytest.approx(0.0025)
        assert usage.output_cost == pytest.approx(0.005)
        assert usage.total_cost == pytest.approx(0.0075)

    def test_gemini_model_cost(self) -> None:
        usage = GenerationUsage(input_tokens=1000, output_tokens=500, model="gemini-2.5-flash")
        assert usage.has_pricing is True
        assert usage.input_cost == pytest.approx(0.00015)
        assert usage.output_cost == pytest.approx(0.00175)

    def test_unknown_model_returns_zero_cost(self) -> None:
        usage = GenerationUsage(input_tokens=1000, output_tokens=500, model="unknown-model")
        assert usage.has_pricing is False
        assert usage.input_cost == 0.0
        assert usage.output_cost == 0.0
        assert usage.total_cost == 0.0
        # Tokens still tracked
        assert usage.total_tokens == 1500

    def test_gpt_4o_mini_cost(self) -> None:
        usage = GenerationUsage(
            input_tokens=1_000_000, output_tokens=1_000_000, model="gpt-4o-mini"
        )
        assert usage.input_cost == pytest.approx(0.15)
        assert usage.output_cost == pytest.approx(0.60)


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_creation(self) -> None:
        resp = LLMResponse(text="hello", input_tokens=10, output_tokens=5, stop_reason="end_turn")
        assert resp.text == "hello"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5
        assert resp.stop_reason == "end_turn"

    def test_frozen(self) -> None:
        resp = LLMResponse(text="hello", input_tokens=10, output_tokens=5, stop_reason="end_turn")
        with pytest.raises(AttributeError):
            resp.text = "changed"  # type: ignore[misc]


class TestResolveProvider:
    """Tests for resolve_provider factory."""

    def test_anthropic_model_creates_anthropic_provider(self) -> None:
        with patch("skill_lab.core.llm.AnthropicProvider") as mock_cls:
            resolve_provider("claude-haiku-4-5-20251001", api_key="test-key")
            mock_cls.assert_called_once_with(api_key="test-key")

    def test_openai_model_creates_openai_provider(self) -> None:
        with patch("skill_lab.core.llm.OpenAIProvider") as mock_cls:
            resolve_provider("gpt-4o", api_key="test-key")
            mock_cls.assert_called_once_with(api_key="test-key")

    def test_gemini_model_creates_gemini_provider(self) -> None:
        with patch("skill_lab.core.llm.GeminiProvider") as mock_cls:
            resolve_provider("gemini-2.5-flash", api_key="test-key")
            mock_cls.assert_called_once_with(api_key="test-key")


class TestAnthropicProvider:
    """Tests for AnthropicProvider.create_message()."""

    def test_create_message(self) -> None:
        pytest.importorskip("anthropic")

        mock_block = MagicMock()
        mock_block.text = "response text"
        mock_msg = MagicMock()
        mock_msg.content = [mock_block]
        mock_msg.usage.input_tokens = 100
        mock_msg.usage.output_tokens = 50
        mock_msg.stop_reason = "end_turn"

        with patch("anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = mock_msg
            provider = AnthropicProvider(api_key="test-key")
            resp = provider.create_message(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                system="You are a helper.",
                prompt="Hello",
            )

        assert resp.text == "response text"
        assert resp.input_tokens == 100
        assert resp.output_tokens == 50
        assert resp.stop_reason == "end_turn"


class TestOpenAIProvider:
    """Tests for OpenAIProvider.create_message()."""

    def test_create_message(self) -> None:
        pytest.importorskip("openai")

        mock_choice = MagicMock()
        mock_choice.message.content = "openai response"
        mock_choice.finish_reason = "stop"
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 200
        mock_usage.completion_tokens = 100
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = mock_response
            provider = OpenAIProvider(api_key="test-key")
            resp = provider.create_message(
                model="gpt-4o-mini",
                max_tokens=2048,
                system="You are a helper.",
                prompt="Hello",
            )

        assert resp.text == "openai response"
        assert resp.input_tokens == 200
        assert resp.output_tokens == 100
        assert resp.stop_reason == "end_turn"

    def test_max_tokens_stop_reason(self) -> None:
        pytest.importorskip("openai")

        mock_choice = MagicMock()
        mock_choice.message.content = "truncated"
        mock_choice.finish_reason = "length"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = mock_response
            provider = OpenAIProvider(api_key="test-key")
            resp = provider.create_message(
                model="gpt-4o-mini",
                max_tokens=2048,
                system="sys",
                prompt="Hello",
            )

        assert resp.stop_reason == "max_tokens"


@contextmanager
def _mock_genai() -> Iterator[MagicMock]:
    """Mock google.generativeai in sys.modules so GeminiProvider can import it."""
    mock = MagicMock()
    with patch.dict("sys.modules", {"google.generativeai": mock}):
        yield mock


class TestGeminiProvider:
    """Tests for GeminiProvider.create_message()."""

    def test_create_message(self) -> None:
        mock_candidate = MagicMock()
        mock_candidate.finish_reason = "STOP"
        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 150
        mock_usage.candidates_token_count = 75
        mock_response = MagicMock()
        mock_response.text = "gemini response"
        mock_response.usage_metadata = mock_usage
        mock_response.candidates = [mock_candidate]

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with _mock_genai() as mock_genai:
            mock_genai.GenerativeModel.return_value = mock_model
            provider = GeminiProvider(api_key="test-key")
            resp = provider.create_message(
                model="gemini-2.5-flash",
                max_tokens=2048,
                system="You are a helper.",
                prompt="Hello",
            )

        assert resp.text == "gemini response"
        assert resp.input_tokens == 150
        assert resp.output_tokens == 75
        assert resp.stop_reason == "end_turn"

    def test_safety_blocked_response(self) -> None:
        """Test that safety-blocked responses return empty text instead of crashing."""
        mock_response = MagicMock()
        type(mock_response).text = property(
            lambda self: (_ for _ in ()).throw(ValueError("blocked"))
        )
        mock_response.usage_metadata = MagicMock(prompt_token_count=100, candidates_token_count=0)
        mock_response.candidates = []

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with _mock_genai() as mock_genai:
            mock_genai.GenerativeModel.return_value = mock_model
            provider = GeminiProvider(api_key="test-key")
            resp = provider.create_message(
                model="gemini-2.5-flash",
                max_tokens=2048,
                system="sys",
                prompt="Hello",
            )

        assert resp.text == ""
        assert resp.input_tokens == 100
        assert resp.stop_reason == "safety"

    def test_max_tokens_stop_reason(self) -> None:
        mock_candidate = MagicMock()
        mock_candidate.finish_reason = "MAX_TOKENS"
        mock_response = MagicMock()
        mock_response.text = "truncated"
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=100, candidates_token_count=2048
        )
        mock_response.candidates = [mock_candidate]

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with _mock_genai() as mock_genai:
            mock_genai.GenerativeModel.return_value = mock_model
            provider = GeminiProvider(api_key="test-key")
            resp = provider.create_message(
                model="gemini-2.5-flash",
                max_tokens=2048,
                system="sys",
                prompt="Hello",
            )

        assert resp.stop_reason == "max_tokens"
