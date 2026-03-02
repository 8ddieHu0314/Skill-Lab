"""Tests for token estimation utility."""

from skill_lab.core.tokens import estimate_tokens


class TestEstimateTokens:
    """Tests for estimate_tokens function."""

    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_string(self):
        # 12 chars / 4 = 3
        assert estimate_tokens("hello world!") == 3

    def test_longer_string(self):
        text = "a" * 100
        assert estimate_tokens(text) == 25

    def test_returns_int(self):
        result = estimate_tokens("some text")
        assert isinstance(result, int)

    def test_never_negative(self):
        assert estimate_tokens("") >= 0
        assert estimate_tokens("x") >= 0
