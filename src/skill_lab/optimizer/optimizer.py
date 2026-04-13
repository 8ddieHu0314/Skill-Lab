"""LLM-powered SKILL.md optimizer.

Uses the LLM provider abstraction to read a SKILL.md, evaluate it with static checks,
and generate an improved version based on failing checks and fix hints.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from skill_lab.core.eval_history import EvalRecord
from skill_lab.core.exceptions import GenerationError
from skill_lab.core.llm import (
    DEFAULT_MODEL,
    GenerationUsage,
    LLMProvider,
    detect_provider_name,
    get_api_key_env_var,
    resolve_provider,
)
from skill_lab.core.models import CheckResult, EvaluationReport, JudgeCriterion
from skill_lab.core.scoring import PATTERN_SCORE_THRESHOLD
from skill_lab.evaluators.static_evaluator import StaticEvaluator

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "optimize_skill.md"

SYSTEM_PROMPT = (
    "You are executing the optimize-skill skill. "
    "Follow the instructions below to optimize the target SKILL.md file. "
    "Output ONLY the complete improved SKILL.md content — no markdown fences, "
    "no explanations, no commentary.\n\n" + _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
)

MAX_BODY_CHARS = 12000

_PATTERNS_DIR = Path(__file__).parent / "patterns"


def _format_failures(results: list[CheckResult]) -> str:
    """Format failing check results into a prompt-ready text block."""
    failures: list[str] = []
    for result in results:
        if not result.passed:
            line = f"- [{result.check_id}] (severity: {result.severity.value}) {result.message}"
            if result.fix:
                line += f"\n  Fix: {result.fix}"
            failures.append(line)
    return "\n".join(failures) if failures else "No failing checks."


def _truncate_content(content: str) -> str:
    """Truncate skill content to MAX_BODY_CHARS with a marker if needed."""
    if len(content) <= MAX_BODY_CHARS:
        return content
    return content[:MAX_BODY_CHARS] + "\n\n[... content truncated ...]"


def _load_patterns_for_criteria(
    criteria: tuple[JudgeCriterion, ...],
    score_threshold: int = PATTERN_SCORE_THRESHOLD,
) -> str:
    """Load spec-sourced pattern files for low-scoring criteria.

    Filters criteria to those scoring at or below `score_threshold`, sorts by
    score ascending (worst first), and loads the matching pattern file from
    ``patterns/{criterion.id}.md``. Criteria without a matching file (e.g.,
    activation criteria) are silently skipped.

    Returns the concatenated pattern text, or an empty string if nothing was
    loaded.
    """
    low_scoring = sorted(
        (c for c in criteria if c.score <= score_threshold),
        key=lambda c: c.score,
    )

    loaded: list[str] = []
    for criterion in low_scoring:
        pattern_file = _PATTERNS_DIR / f"{criterion.id}.md"
        if pattern_file.exists():
            loaded.append(pattern_file.read_text(encoding="utf-8").rstrip())

    return "\n\n".join(loaded)


@dataclass(frozen=True)
class OptimizationResult:
    """Result of an optimization operation."""

    original_content: str
    optimized_content: str
    original_score: float
    optimized_score: float
    original_failures: int
    optimized_failures: int
    usage: GenerationUsage | None


class SkillOptimizer:
    """Optimizes SKILL.md files using an LLM."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        """Initialize the optimizer.

        Args:
            model: Model ID to use for optimization.
            api_key: API key. If None, uses the appropriate env var for the provider.
            provider: Optional pre-built LLMProvider. If None, one is resolved from
                the model ID.
        """
        self._model = model
        self._provider = provider or resolve_provider(model, api_key=api_key)
        self.last_usage: GenerationUsage | None = None

    def optimize(self, skill_path: Path) -> OptimizationResult:
        """Run full optimization pipeline: evaluate -> LLM -> re-evaluate.

        Args:
            skill_path: Path to the skill directory (must contain SKILL.md).

        Returns:
            OptimizationResult with original and optimized content and scores.

        Raises:
            GenerationError: If optimization fails.
        """
        original_content = self._read_skill_md(skill_path)

        # Evaluate current state
        before_report = self._evaluate(skill_path)

        # Build prompt and call LLM
        prompt = self._build_prompt(original_content, before_report)
        optimized_content = self._run_llm(prompt)

        # Re-evaluate optimized content
        after_report = self._re_evaluate(optimized_content, skill_path)

        return OptimizationResult(
            original_content=original_content,
            optimized_content=optimized_content,
            original_score=before_report.quality_score,
            optimized_score=after_report.quality_score,
            original_failures=before_report.checks_failed,
            optimized_failures=after_report.checks_failed,
            usage=self.last_usage,
        )

    def optimize_from_history(
        self,
        skill_path: Path,
        eval_record: EvalRecord,
    ) -> OptimizationResult:
        """Run optimization using a pre-existing evaluation record.

        Unlike optimize(), this does NOT run its own internal evaluation —
        it reads static failures and judge feedback from the provided history.

        Args:
            skill_path: Path to the skill directory (must contain SKILL.md).
            eval_record: Previously persisted evaluation record.

        Returns:
            OptimizationResult with original and optimized content and scores.

        Raises:
            GenerationError: If optimization fails.
        """
        original_content = self._read_skill_md(skill_path)

        # Build prompt from history (static + judge)
        prompt = self._build_prompt_from_history(original_content, eval_record)
        optimized_content = self._run_llm(prompt)

        # Re-evaluate optimized content (fresh StaticEvaluator)
        after_report = self._re_evaluate(optimized_content, skill_path)

        return OptimizationResult(
            original_content=original_content,
            optimized_content=optimized_content,
            original_score=eval_record.report.quality_score,
            optimized_score=after_report.quality_score,
            original_failures=eval_record.report.checks_failed,
            optimized_failures=after_report.checks_failed,
            usage=self.last_usage,
        )

    def _read_skill_md(self, skill_path: Path) -> str:
        """Read SKILL.md content, raising GenerationError if missing."""
        try:
            return (skill_path / "SKILL.md").read_text(encoding="utf-8")
        except FileNotFoundError:
            raise GenerationError(
                "SKILL.md not found",
                skill_path=str(skill_path),
                suggestion="Ensure the skill directory contains a SKILL.md file.",
            ) from None

    def _run_llm(self, prompt: str) -> str:
        """Call LLM and parse response into valid SKILL.md content."""
        response_text = self._call_api(prompt)
        return self._parse_response(response_text)

    def _build_prompt_from_history(
        self,
        skill_content: str,
        eval_record: EvalRecord,
    ) -> str:
        """Build user message from eval history, including judge feedback.

        Args:
            skill_content: Full content of the SKILL.md file.
            eval_record: Evaluation record with static results and optional judge.

        Returns:
            Formatted user message for the API call.
        """
        report = eval_record.report
        failures_text = _format_failures(report.results)

        # Judge feedback section
        judge_text = ""
        if eval_record.judge is not None:
            judge = eval_record.judge
            judge_lines = [
                f"LLM Judge Score: {judge.judge_score}/100 ({judge.verdict})",
                f"  Activation Quality: {judge.activation_score}/100",
                f"  Instruction Quality: {judge.instruction_score}/100",
                "",
                "Criterion Scores:",
            ]
            for c in judge.criteria:
                judge_lines.append(f"  - {c.name} ({c.axis}): {c.score}/4 — {c.reasoning}")
            if judge.suggestions:
                judge_lines.append("")
                judge_lines.append("Judge Suggestions:")
                for s in judge.suggestions:
                    judge_lines.append(f"  - {s}")
            judge_text = "\n".join(judge_lines)

        # Pattern loading: inject spec-sourced before/after transformations
        # for criteria scoring at or below PATTERN_SCORE_THRESHOLD.
        patterns_text = ""
        if eval_record.judge is not None:
            patterns_text = _load_patterns_for_criteria(eval_record.judge.criteria)

        content = _truncate_content(skill_content)

        parts = [
            "Optimize this SKILL.md file.\n",
            f"Current score: {report.quality_score}/100 ({report.checks_failed} failing checks)\n",
            f"--- Failing Checks ---\n{failures_text}\n",
        ]
        if judge_text:
            parts.append(f"--- LLM Judge Feedback ---\n{judge_text}\n")
        if patterns_text:
            parts.append(f"--- Relevant Patterns ---\n{patterns_text}\n")
        parts.append(f"--- Current SKILL.md ---\n{content}")

        return "\n".join(parts)

    def _evaluate(
        self,
        skill_path: Path,
        exclude_check_ids: list[str] | None = None,
    ) -> EvaluationReport:
        """Run static evaluation on a skill.

        Args:
            skill_path: Path to the skill directory.
            exclude_check_ids: Optional check IDs to skip.

        Returns:
            EvaluationReport with check results and score.
        """
        evaluator = StaticEvaluator(exclude_check_ids=exclude_check_ids)
        return evaluator.evaluate(skill_path)

    def _build_prompt(
        self,
        skill_content: str,
        report: EvaluationReport,
    ) -> str:
        """Build the user message with skill content and evaluation failures.

        Args:
            skill_content: Full content of the SKILL.md file.
            report: Evaluation report with check results.

        Returns:
            Formatted user message for the API call.
        """
        failures_text = _format_failures(report.results)
        content = _truncate_content(skill_content)

        return (
            f"Optimize this SKILL.md file.\n\n"
            f"Current score: {report.quality_score}/100 "
            f"({report.checks_failed} failing checks)\n\n"
            f"--- Failing Checks ---\n"
            f"{failures_text}\n\n"
            f"--- Current SKILL.md ---\n"
            f"{content}"
        )

    def _call_api(self, prompt: str) -> str:
        """Call the LLM provider to generate optimized SKILL.md.

        Args:
            prompt: The user message to send.

        Returns:
            The model's response text.

        Raises:
            GenerationError: If the API call fails.
        """
        try:
            response = self._provider.create_message(
                model=self._model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                prompt=prompt,
            )
            if response.stop_reason == "max_tokens":
                raise GenerationError(
                    "Model output was truncated (max_tokens limit reached). "
                    "The skill may be too large to optimize in one pass.",
                    suggestion="Try a model with a larger output window or shorten the skill.",
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
            if not response.text:
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

    def _parse_response(self, response_text: str) -> str:
        """Parse and validate the API response.

        Strips markdown fences if present and validates the output
        looks like a SKILL.md file.

        Args:
            response_text: Raw response text from the API.

        Returns:
            Cleaned SKILL.md content.

        Raises:
            GenerationError: If response is not valid SKILL.md content.
        """
        text = response_text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # Remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]  # Remove closing fence
            text = "\n".join(lines).strip()

        # Validate it looks like a SKILL.md (starts with frontmatter)
        if not text.startswith("---"):
            raise GenerationError(
                "Optimized output does not start with frontmatter delimiter '---'",
                suggestion="The model returned unexpected format. Try running again.",
            )

        # Ensure it ends with a newline
        if not text.endswith("\n"):
            text += "\n"

        return text

    def _re_evaluate(
        self,
        optimized_content: str,
        original_skill_path: Path,
    ) -> EvaluationReport:
        """Write optimized content to a temp directory and re-evaluate.

        Creates a temporary skill directory with the optimized SKILL.md
        and symlinks to the original subdirectories (scripts/, references/,
        assets/) so path-checking checks work correctly.

        Args:
            optimized_content: The optimized SKILL.md content.
            original_skill_path: Path to the original skill directory.

        Returns:
            EvaluationReport for the optimized skill.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Write optimized SKILL.md
            (tmp_path / "SKILL.md").write_text(optimized_content, encoding="utf-8")

            # Symlink subdirectories from original skill
            for subdir in ("scripts", "references", "assets"):
                original_subdir = original_skill_path / subdir
                if original_subdir.exists():
                    target = tmp_path / subdir
                    try:
                        os.symlink(original_subdir, target)
                    except OSError:
                        # Fallback for platforms where symlinks fail (e.g. Windows)
                        shutil.copytree(original_subdir, target)

            # Skip the directory-name check: the temp dir name doesn't match the
            # skill's frontmatter name, which would always fail this check and
            # produce a misleadingly low optimized_score.
            return self._evaluate(tmp_path, exclude_check_ids=["naming.matches-directory"])
