"""LLM-powered SKILL.md optimizer.

Uses the Anthropic SDK to read a SKILL.md, evaluate it with static checks,
and generate an improved version based on failing checks and fix hints.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from skill_lab.core.exceptions import GenerationError
from skill_lab.core.models import EvaluationReport
from skill_lab.evaluators.static_evaluator import StaticEvaluator
from skill_lab.triggers.generator import DEFAULT_MODEL, GenerationUsage

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "optimize_skill.md"

SYSTEM_PROMPT = (
    "You are executing the optimize-skill skill. "
    "Follow the instructions below to optimize the target SKILL.md file. "
    "Output ONLY the complete improved SKILL.md content — no markdown fences, "
    "no explanations, no commentary.\n\n" + _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
)

MAX_BODY_CHARS = 12000


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
    """Optimizes SKILL.md files using the Anthropic API."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
    ) -> None:
        """Initialize the optimizer.

        Args:
            model: Anthropic model ID to use for optimization.
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
        """
        import anthropic

        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)
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
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            raise GenerationError(
                "SKILL.md not found",
                skill_path=str(skill_path),
                suggestion="Ensure the skill directory contains a SKILL.md file.",
            )

        original_content = skill_md.read_text(encoding="utf-8")

        # Evaluate current state
        before_report = self._evaluate(skill_path)

        # Build prompt and call LLM
        prompt = self._build_prompt(original_content, before_report)
        response_text = self._call_api(prompt)
        optimized_content = self._parse_response(response_text)

        # Re-evaluate optimized content
        after_report = self._re_evaluate(optimized_content, skill_path)

        before_failures = before_report.checks_failed
        after_failures = after_report.checks_failed

        return OptimizationResult(
            original_content=original_content,
            optimized_content=optimized_content,
            original_score=before_report.quality_score,
            optimized_score=after_report.quality_score,
            original_failures=before_failures,
            optimized_failures=after_failures,
            usage=self.last_usage,
        )

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
        # Collect failing checks
        failures: list[str] = []
        for result in report.results:
            if not result.passed:
                line = f"- [{result.check_id}] (severity: {result.severity.value}) {result.message}"
                if result.fix:
                    line += f"\n  Fix: {result.fix}"
                failures.append(line)

        failures_text = "\n".join(failures) if failures else "No failing checks."

        # Truncate body if extremely large
        content = skill_content[:MAX_BODY_CHARS]
        if len(skill_content) > MAX_BODY_CHARS:
            content += "\n\n[... content truncated ...]"

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
        """Call the Anthropic API to generate optimized SKILL.md.

        Args:
            prompt: The user message to send.

        Returns:
            The model's response text.

        Raises:
            GenerationError: If the API call fails.
        """
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            if message.stop_reason == "max_tokens":
                raise GenerationError(
                    "Model output was truncated (max_tokens limit reached). "
                    "The skill may be too large to optimize in one pass.",
                    suggestion="Try a model with a larger output window or shorten the skill.",
                )
            # Capture token usage
            self.last_usage = GenerationUsage(
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                model=self._model,
            )
            # Extract text from content blocks
            text_parts = [block.text for block in message.content if hasattr(block, "text")]
            if not text_parts:
                raise GenerationError("API returned empty response")
            return "\n".join(text_parts)
        except GenerationError:
            raise
        except Exception as e:
            raise GenerationError(
                f"API call failed: {e}",
                suggestion="Check your ANTHROPIC_API_KEY and network connection.",
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
