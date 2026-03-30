"""LLM-as-judge quality assessment for agent skills.

Evaluates a SKILL.md against a structured rubric with 8 criteria
across two axes (Activation Quality and Instruction Quality).
"""

from __future__ import annotations

import json
from pathlib import Path

from skill_lab.core.exceptions import GenerationError
from skill_lab.core.llm import (
    DEFAULT_MODEL,
    GenerationUsage,
    LLMProvider,
    detect_provider_name,
    get_api_key_env_var,
    resolve_provider,
)
from skill_lab.core.models import JudgeCriterion, JudgeResult, Skill
from skill_lab.parsers.skill_parser import parse_skill

_RUBRIC_PATH = Path(__file__).parent / "rubric.md"

SYSTEM_PROMPT = (
    "You are executing the skill-quality-judge skill. "
    "Follow the rubric below to evaluate the target SKILL.md file. "
    "Output ONLY valid JSON — no markdown fences, no explanations, no commentary.\n\n"
    + _RUBRIC_PATH.read_text(encoding="utf-8")
)

MAX_BODY_CHARS = 8000

# Canonical criterion definitions: (id, display name, axis)
CRITERIA_DEFS: tuple[tuple[str, str, str], ...] = (
    ("intent_clarity", "Intent Clarity", "activation"),
    ("trigger_coverage", "Trigger Coverage", "activation"),
    ("scope_precision", "Scope Precision", "activation"),
    ("distinctiveness", "Distinctiveness", "activation"),
    ("domain_expertise", "Domain Expertise", "instruction"),
    ("cognitive_efficiency", "Cognitive Efficiency", "instruction"),
    ("procedural_clarity", "Procedural Clarity", "instruction"),
    ("error_resilience", "Error Resilience", "instruction"),
)

VERDICT_BANDS: tuple[tuple[float, str], ...] = (
    (90.0, "Excellent"),
    (75.0, "Good"),
    (50.0, "Needs work"),
    (0.0, "Poor"),
)


def _compute_verdict(score: float) -> str:
    """Map a 0-100 score to a verdict label."""
    for threshold, label in VERDICT_BANDS:
        if score >= threshold:
            return label
    return "Poor"


class SkillJudge:
    """Evaluates skills using an LLM-as-judge approach."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        self._model = model
        self._provider = provider or resolve_provider(model, api_key=api_key)
        self.last_usage: GenerationUsage | None = None

    def review(self, skill_path: Path, skill: Skill | None = None) -> JudgeResult:
        """Run LLM judge evaluation on a skill.

        Args:
            skill_path: Path to the skill directory containing SKILL.md.
            skill: Pre-parsed Skill object. If None, parses from skill_path.

        Returns:
            JudgeResult with per-criterion scores and overall scores.

        Raises:
            GenerationError: If the LLM call or response parsing fails.
        """
        if skill is None:
            skill = parse_skill(skill_path)

        skill_name = skill.metadata.name if skill.metadata else skill_path.name
        description = skill.metadata.description if skill.metadata else ""
        body = skill.body

        prompt = self._build_prompt(skill_name, description, body)
        response_text = self._call_api(prompt)

        try:
            return self._parse_response(response_text)
        except GenerationError:
            # Retry once on JSON parse failure
            response_text = self._call_api(prompt)
            return self._parse_response(response_text)

    def _build_prompt(self, skill_name: str, description: str, body: str) -> str:
        """Build the user prompt with skill content."""
        truncated_body = body[:MAX_BODY_CHARS]
        if len(body) > MAX_BODY_CHARS:
            truncated_body += "\n\n[... content truncated ...]"

        return (
            f"Evaluate this skill:\n\n"
            f"Skill Name: {skill_name}\n"
            f"Description: {description}\n\n"
            f"--- SKILL.md body ---\n"
            f"{truncated_body}"
        )

    def _call_api(self, prompt: str) -> str:
        """Call the LLM provider and return response text."""
        try:
            response = self._provider.create_message(
                model=self._model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                prompt=prompt,
            )
            self.last_usage = GenerationUsage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                model=self._model,
            )
            if response.stop_reason == "safety":
                raise GenerationError(
                    "Response blocked by content safety filters",
                    suggestion="Try rephrasing the skill content or using a different model.",
                )
            if not response.text.strip():
                raise GenerationError("API returned empty response")
            return response.text
        except GenerationError:
            raise
        except Exception as e:
            provider_name = detect_provider_name(self._model)
            env_var = get_api_key_env_var(provider_name)
            raise GenerationError(
                f"API call failed: {e}",
                suggestion=f"Check your {env_var} and network connection.",
            ) from e

    def _parse_response(self, response_text: str) -> JudgeResult:
        """Parse JSON response into JudgeResult."""
        text = response_text.strip()

        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise GenerationError(
                f"Failed to parse judge response as JSON: {e}",
                suggestion="The model returned invalid JSON. Try running again.",
            ) from e

        if not isinstance(data, dict):
            raise GenerationError(
                f"Expected JSON object, got {type(data).__name__}",
            )

        return self._build_result(data)

    def _build_result(self, data: dict[str, object]) -> JudgeResult:
        """Validate parsed JSON and construct JudgeResult."""
        raw_criteria = data.get("criteria")
        if not isinstance(raw_criteria, list) or len(raw_criteria) == 0:
            raise GenerationError("Judge response missing or empty 'criteria' array")

        response_lookup: dict[str, dict[str, object]] = {}
        for item in raw_criteria:
            if isinstance(item, dict) and "id" in item:
                response_lookup[str(item["id"])] = item

        criteria: list[JudgeCriterion] = []
        for crit_id, crit_name, crit_axis in CRITERIA_DEFS:
            item = response_lookup.get(crit_id)
            if item is None:
                raise GenerationError(
                    f"Judge response missing criterion '{crit_id}'",
                    suggestion="The model returned incomplete output. Try running again.",
                )
            raw_score = item.get("score")
            # Accept both int and float (some models return 3.0 instead of 3)
            if isinstance(raw_score, float):
                score = int(raw_score)
            elif isinstance(raw_score, int):
                score = raw_score
            else:
                raise GenerationError(
                    f"Criterion '{crit_id}' has invalid score type: {type(raw_score).__name__}",
                )
            if not (0 <= score <= 4):
                raise GenerationError(
                    f"Criterion '{crit_id}' has invalid score: {score} (expected 0-4)",
                )
            reasoning = str(item.get("reasoning", ""))
            criteria.append(
                JudgeCriterion(
                    id=crit_id,
                    name=crit_name,
                    axis=crit_axis,
                    score=score,
                    reasoning=reasoning,
                )
            )

        activation_raw = sum(c.score for c in criteria if c.axis == "activation")
        instruction_raw = sum(c.score for c in criteria if c.axis == "instruction")

        activation_score = round(activation_raw / 16 * 100, 1)
        instruction_score = round(instruction_raw / 16 * 100, 1)
        judge_score = round((activation_score + instruction_score) / 2, 1)

        verdict = _compute_verdict(judge_score)

        raw_suggestions = data.get("suggestions")
        if isinstance(raw_suggestions, list):
            suggestions = tuple(str(s) for s in raw_suggestions if isinstance(s, str))
        else:
            suggestions = ()

        return JudgeResult(
            criteria=tuple(criteria),
            activation_score=activation_score,
            instruction_score=instruction_score,
            judge_score=judge_score,
            verdict=verdict,
            suggestions=suggestions,
        )
