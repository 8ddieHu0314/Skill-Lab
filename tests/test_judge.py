"""Tests for LLM-as-judge quality assessment."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skill_lab.core.exceptions import GenerationError
from skill_lab.core.llm import LLMResponse
from skill_lab.core.models import JudgeCriterion, JudgeResult
from skill_lab.judge.judge import (
    CRITERIA_DEFS,
    SkillJudge,
    _compute_verdict,
)


def _make_response_json(
    scores: tuple[int, ...] = (3, 2, 3, 2, 3, 2, 3, 1, 2),
    suggestions: list[str] | None = None,
) -> str:
    """Build a valid judge response JSON string."""
    criteria = []
    for (crit_id, _, _), score in zip(CRITERIA_DEFS, scores):
        criteria.append(
            {
                "id": crit_id,
                "score": score,
                "reasoning": f"Score {score} for {crit_id}.",
            }
        )
    return json.dumps(
        {
            "criteria": criteria,
            "suggestions": suggestions or ["Improve trigger coverage.", "Add gotchas section."],
        }
    )


def _mock_provider(response_text: str) -> MagicMock:
    """Create a mock LLM provider returning the given text."""
    provider = MagicMock()
    provider.create_message.return_value = LLMResponse(
        text=response_text,
        input_tokens=1000,
        output_tokens=500,
        stop_reason="end_turn",
    )
    return provider


class TestSkillJudge:
    """Tests for the SkillJudge class."""

    def test_review_returns_judge_result(self, valid_skill_path: Path) -> None:
        response = _make_response_json()
        provider = _mock_provider(response)
        judge = SkillJudge(provider=provider)

        result = judge.review(valid_skill_path)

        assert isinstance(result, JudgeResult)
        assert len(result.criteria) == 9
        assert result.activation_score >= 0
        assert result.instruction_score >= 0
        assert result.judge_score >= 0
        assert result.verdict in ("Excellent", "Good", "Needs work", "Poor")

    def test_review_tracks_usage(self, valid_skill_path: Path) -> None:
        response = _make_response_json()
        provider = _mock_provider(response)
        judge = SkillJudge(provider=provider)

        judge.review(valid_skill_path)

        assert judge.last_usage is not None
        assert judge.last_usage.input_tokens == 1000
        assert judge.last_usage.output_tokens == 500

    def test_review_passes_skill_content_to_provider(self, valid_skill_path: Path) -> None:
        response = _make_response_json()
        provider = _mock_provider(response)
        judge = SkillJudge(provider=provider)

        judge.review(valid_skill_path)

        call_kwargs = provider.create_message.call_args.kwargs
        assert "creating-reports" in call_kwargs["prompt"]
        assert call_kwargs["max_tokens"] == 2048

    def test_review_retries_on_parse_failure(self, valid_skill_path: Path) -> None:
        """First call returns bad JSON, retry returns valid JSON."""
        valid = _make_response_json()
        provider = MagicMock()
        provider.create_message.side_effect = [
            LLMResponse(
                text="not json", input_tokens=100, output_tokens=50, stop_reason="end_turn"
            ),
            LLMResponse(text=valid, input_tokens=100, output_tokens=50, stop_reason="end_turn"),
        ]
        judge = SkillJudge(provider=provider)

        result = judge.review(valid_skill_path)

        assert isinstance(result, JudgeResult)
        assert provider.create_message.call_count == 2

    def test_review_raises_after_two_parse_failures(self, valid_skill_path: Path) -> None:
        """Both calls return bad JSON — should raise."""
        provider = MagicMock()
        provider.create_message.return_value = LLMResponse(
            text="still not json", input_tokens=100, output_tokens=50, stop_reason="end_turn"
        )
        judge = SkillJudge(provider=provider)

        with pytest.raises(GenerationError, match="Failed to parse"):
            judge.review(valid_skill_path)

        assert provider.create_message.call_count == 2

    def test_review_safety_block_raises(self, valid_skill_path: Path) -> None:
        provider = MagicMock()
        provider.create_message.return_value = LLMResponse(
            text="", input_tokens=100, output_tokens=0, stop_reason="safety"
        )
        judge = SkillJudge(provider=provider)

        with pytest.raises(GenerationError, match="safety"):
            judge.review(valid_skill_path)

    def test_review_empty_response_raises(self, valid_skill_path: Path) -> None:
        provider = MagicMock()
        provider.create_message.return_value = LLMResponse(
            text="   ", input_tokens=100, output_tokens=0, stop_reason="end_turn"
        )
        judge = SkillJudge(provider=provider)

        with pytest.raises(GenerationError, match="empty"):
            judge.review(valid_skill_path)

    def test_review_api_error_raises(self, valid_skill_path: Path) -> None:
        provider = MagicMock()
        provider.create_message.side_effect = RuntimeError("connection refused")
        judge = SkillJudge(provider=provider)

        with pytest.raises(GenerationError, match="API call failed"):
            judge.review(valid_skill_path)


class TestScoreCalculation:
    """Tests for score calculation logic."""

    def test_perfect_scores(self, valid_skill_path: Path) -> None:
        response = _make_response_json(scores=(4, 4, 4, 4, 4, 4, 4, 4, 4))
        provider = _mock_provider(response)
        judge = SkillJudge(provider=provider)

        result = judge.review(valid_skill_path)

        assert result.activation_score == 100.0
        assert result.instruction_score == 100.0
        assert result.judge_score == 100.0
        assert result.verdict == "Excellent"

    def test_zero_scores(self, valid_skill_path: Path) -> None:
        response = _make_response_json(scores=(0, 0, 0, 0, 0, 0, 0, 0, 0))
        provider = _mock_provider(response)
        judge = SkillJudge(provider=provider)

        result = judge.review(valid_skill_path)

        assert result.activation_score == 0.0
        assert result.instruction_score == 0.0
        assert result.judge_score == 0.0
        assert result.verdict == "Poor"

    def test_mixed_scores(self, valid_skill_path: Path) -> None:
        # activation: 3+2+3+2 = 10/16 = 62.5%
        # instruction: 3+2+3+1+2 = 11/20 = 55.0%
        # judge: (62.5 + 55.0) / 2 = 58.8%
        response = _make_response_json(scores=(3, 2, 3, 2, 3, 2, 3, 1, 2))
        provider = _mock_provider(response)
        judge = SkillJudge(provider=provider)

        result = judge.review(valid_skill_path)

        assert result.activation_score == 62.5
        assert result.instruction_score == 55.0
        assert result.verdict == "Needs work"

    def test_verdict_excellent(self) -> None:
        assert _compute_verdict(95.0) == "Excellent"
        assert _compute_verdict(90.0) == "Excellent"

    def test_verdict_good(self) -> None:
        assert _compute_verdict(85.0) == "Good"
        assert _compute_verdict(75.0) == "Good"

    def test_verdict_needs_work(self) -> None:
        assert _compute_verdict(60.0) == "Needs work"
        assert _compute_verdict(50.0) == "Needs work"

    def test_verdict_poor(self) -> None:
        assert _compute_verdict(30.0) == "Poor"
        assert _compute_verdict(0.0) == "Poor"


class TestParseResponse:
    """Tests for response parsing."""

    def test_valid_json_parsed(self, valid_skill_path: Path) -> None:
        response = _make_response_json()
        provider = _mock_provider(response)
        judge = SkillJudge(provider=provider)

        result = judge.review(valid_skill_path)

        assert len(result.criteria) == 9
        assert result.criteria[0].id == "intent_clarity"
        assert result.criteria[0].axis == "activation"
        assert result.criteria[4].id == "domain_expertise"
        assert result.criteria[4].axis == "instruction"
        assert result.criteria[8].id == "progressive_disclosure"
        assert result.criteria[8].axis == "instruction"

    def test_markdown_fences_stripped(self, valid_skill_path: Path) -> None:
        raw_json = _make_response_json()
        fenced = f"```json\n{raw_json}\n```"
        provider = _mock_provider(fenced)
        judge = SkillJudge(provider=provider)

        result = judge.review(valid_skill_path)

        assert len(result.criteria) == 9

    def test_invalid_json_raises(self, valid_skill_path: Path) -> None:
        provider = _mock_provider("this is not json")
        judge = SkillJudge(provider=provider)

        with pytest.raises(GenerationError, match="Failed to parse"):
            judge.review(valid_skill_path)

    def test_missing_criteria_raises(self, valid_skill_path: Path) -> None:
        data = json.dumps({"criteria": [], "suggestions": []})
        provider = _mock_provider(data)
        judge = SkillJudge(provider=provider)

        with pytest.raises(GenerationError, match="missing or empty"):
            judge.review(valid_skill_path)

    def test_missing_criterion_id_raises(self, valid_skill_path: Path) -> None:
        # Only 8 of 9 criteria
        criteria = []
        for crit_id, _, _ in CRITERIA_DEFS[:8]:
            criteria.append({"id": crit_id, "score": 3, "reasoning": "ok"})
        data = json.dumps({"criteria": criteria, "suggestions": []})
        provider = _mock_provider(data)
        judge = SkillJudge(provider=provider)

        with pytest.raises(GenerationError, match="missing criterion"):
            judge.review(valid_skill_path)

    def test_invalid_score_range_raises(self, valid_skill_path: Path) -> None:
        criteria = []
        for i, (crit_id, _, _) in enumerate(CRITERIA_DEFS):
            score = 5 if i == 0 else 3  # First criterion has invalid score
            criteria.append({"id": crit_id, "score": score, "reasoning": "ok"})
        data = json.dumps({"criteria": criteria, "suggestions": []})
        provider = _mock_provider(data)
        judge = SkillJudge(provider=provider)

        with pytest.raises(GenerationError, match="invalid score"):
            judge.review(valid_skill_path)

    def test_float_score_accepted(self, valid_skill_path: Path) -> None:
        """Models sometimes return 3.0 instead of 3."""
        criteria = []
        for crit_id, _, _ in CRITERIA_DEFS:
            criteria.append({"id": crit_id, "score": 3.0, "reasoning": "ok"})
        data = json.dumps({"criteria": criteria, "suggestions": []})
        provider = _mock_provider(data)
        judge = SkillJudge(provider=provider)

        result = judge.review(valid_skill_path)

        assert all(c.score == 3 for c in result.criteria)

    def test_non_integer_float_score_raises(self, valid_skill_path: Path) -> None:
        """Scores like 3.5 should be rejected, not silently truncated."""
        criteria = []
        for i, (crit_id, _, _) in enumerate(CRITERIA_DEFS):
            score = 3.5 if i == 0 else 3
            criteria.append({"id": crit_id, "score": score, "reasoning": "ok"})
        data = json.dumps({"criteria": criteria, "suggestions": []})
        provider = _mock_provider(data)
        judge = SkillJudge(provider=provider)

        with pytest.raises(GenerationError, match="non-integer score"):
            judge.review(valid_skill_path)

    def test_suggestions_parsed(self, valid_skill_path: Path) -> None:
        response = _make_response_json(
            suggestions=["Add gotchas.", "Broaden triggers.", "Include examples."]
        )
        provider = _mock_provider(response)
        judge = SkillJudge(provider=provider)

        result = judge.review(valid_skill_path)

        assert len(result.suggestions) == 3
        assert "gotchas" in result.suggestions[0].lower()

    def test_missing_suggestions_defaults_empty(self, valid_skill_path: Path) -> None:
        criteria = []
        for crit_id, _, _ in CRITERIA_DEFS:
            criteria.append({"id": crit_id, "score": 3, "reasoning": "ok"})
        data = json.dumps({"criteria": criteria})  # No suggestions key
        provider = _mock_provider(data)
        judge = SkillJudge(provider=provider)

        result = judge.review(valid_skill_path)

        assert result.suggestions == ()


class TestPromptBuilding:
    """Tests for prompt construction."""

    def test_prompt_includes_skill_content(self, valid_skill_path: Path) -> None:
        response = _make_response_json()
        provider = _mock_provider(response)
        judge = SkillJudge(provider=provider)

        judge.review(valid_skill_path)

        prompt = provider.create_message.call_args.kwargs["prompt"]
        assert "creating-reports" in prompt
        assert "SKILL.md body" in prompt

    def test_long_body_truncated(self, tmp_path: Path) -> None:
        """Bodies over MAX_BODY_CHARS are truncated."""
        skill_dir = tmp_path / "long-skill"
        skill_dir.mkdir()
        long_body = "x" * 20000
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: long-skill\ndescription: A skill\n---\n{long_body}"
        )

        response = _make_response_json()
        provider = _mock_provider(response)
        judge = SkillJudge(provider=provider)

        judge.review(skill_dir)

        prompt = provider.create_message.call_args.kwargs["prompt"]
        assert "[... content truncated ...]" in prompt
