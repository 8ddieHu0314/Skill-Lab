"""Unit tests for LLM-powered SKILL.md optimization."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from skill_lab.commands.optimize import _build_diff_text, _increment_patch
from skill_lab.core.eval_history import EvalRecord, save_eval
from skill_lab.core.exceptions import GenerationError
from skill_lab.core.llm import LLMResponse
from skill_lab.core.models import (
    CheckResult,
    EvalDimension,
    EvaluationReport,
    JudgeCriterion,
    JudgeResult,
    Severity,
)
from skill_lab.optimizer.optimizer import (
    MAX_BODY_CHARS,
    OptimizationResult,
    SkillOptimizer,
)

# Sample optimized SKILL.md that a model might return
OPTIMIZED_SKILL_MD = """\
---
name: creating-reports
description: >-
  Use when the user needs to generate, format, or export reports.
  Designed for creating structured reports from data sources.
license: MIT
---

# Creating Reports

This skill helps generate reports from various data sources.

## Usage

Use this skill when you need to:
- Generate formatted reports
- Export data to different formats
- Create summaries from raw data

## Examples

```python
# Generate a CSV report
report = generate_report(data, format="csv")
```
"""


def _mock_llm_response(text: str) -> LLMResponse:
    """Create a mock LLMResponse."""
    return LLMResponse(
        text=text,
        input_tokens=500,
        output_tokens=300,
        stop_reason="end_turn",
    )


@pytest.fixture
def mock_provider() -> MagicMock:
    """Create a mock LLMProvider."""
    provider = MagicMock()
    provider.create_message.return_value = _mock_llm_response(OPTIMIZED_SKILL_MD)
    return provider


@pytest.fixture
def optimizer(mock_provider: MagicMock) -> SkillOptimizer:
    """Create a SkillOptimizer with a mocked provider."""
    opt = SkillOptimizer(provider=mock_provider)
    return opt


class TestSkillOptimizer:
    """Tests for the SkillOptimizer class."""

    def test_optimize_returns_result(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test that optimize() returns an OptimizationResult."""
        result = optimizer.optimize(valid_skill_path)

        assert isinstance(result, OptimizationResult)
        assert result.original_content != ""
        assert result.optimized_content != ""
        assert isinstance(result.original_score, float)
        assert isinstance(result.optimized_score, float)
        assert 0 <= result.original_score <= 100
        assert 0 <= result.optimized_score <= 100

    def test_optimize_tracks_usage(self, optimizer: SkillOptimizer, valid_skill_path: Path) -> None:
        """Test that token usage is tracked after optimization."""
        result = optimizer.optimize(valid_skill_path)

        assert result.usage is not None
        assert result.usage.input_tokens == 500
        assert result.usage.output_tokens == 300
        assert result.usage.total_tokens == 800

    def test_optimize_missing_skill_md(self, optimizer: SkillOptimizer, tmp_path: Path) -> None:
        """Test error when SKILL.md doesn't exist."""
        empty_dir = tmp_path / "no-skill"
        empty_dir.mkdir()

        with pytest.raises(GenerationError, match="SKILL.md not found"):
            optimizer.optimize(empty_dir)

    def test_optimize_handles_api_error(
        self, optimizer: SkillOptimizer, mock_provider: MagicMock, valid_skill_path: Path
    ) -> None:
        """Test error handling when API call fails."""
        mock_provider.create_message.side_effect = Exception("Connection error")

        with pytest.raises(GenerationError, match="API call failed"):
            optimizer.optimize(valid_skill_path)

    def test_optimize_handles_empty_response(
        self, optimizer: SkillOptimizer, mock_provider: MagicMock, valid_skill_path: Path
    ) -> None:
        """Test error handling for empty API response."""
        mock_provider.create_message.return_value = LLMResponse(
            text="",
            input_tokens=100,
            output_tokens=0,
            stop_reason="end_turn",
        )

        with pytest.raises(GenerationError, match="empty response"):
            optimizer.optimize(valid_skill_path)

    def test_optimize_raises_on_max_tokens(
        self, optimizer: SkillOptimizer, mock_provider: MagicMock, valid_skill_path: Path
    ) -> None:
        """Test error raised when model output is truncated by max_tokens limit."""
        mock_provider.create_message.return_value = LLMResponse(
            text="---\nname: test\n---\ntruncated...",
            input_tokens=500,
            output_tokens=8192,
            stop_reason="max_tokens",
        )

        with pytest.raises(GenerationError, match="truncated"):
            optimizer.optimize(valid_skill_path)

    def test_optimize_strips_markdown_fences(
        self, optimizer: SkillOptimizer, mock_provider: MagicMock, valid_skill_path: Path
    ) -> None:
        """Test that markdown code fences are stripped from response."""
        fenced = f"```yaml\n{OPTIMIZED_SKILL_MD}\n```"
        mock_provider.create_message.return_value = _mock_llm_response(fenced)

        result = optimizer.optimize(valid_skill_path)
        assert not result.optimized_content.startswith("```")
        assert result.optimized_content.startswith("---")

    def test_optimize_rejects_invalid_response(
        self, optimizer: SkillOptimizer, mock_provider: MagicMock, valid_skill_path: Path
    ) -> None:
        """Test error when response doesn't look like SKILL.md."""
        mock_provider.create_message.return_value = _mock_llm_response(
            "This is not a valid SKILL.md file, just some text."
        )

        with pytest.raises(GenerationError, match="does not start with frontmatter"):
            optimizer.optimize(valid_skill_path)

    def test_optimize_preserves_subdirectories(
        self, optimizer: SkillOptimizer, tmp_path: Path
    ) -> None:
        """Test that re-evaluation can see scripts/references/assets."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill\n---\n\nBody content\n"
        )
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.sh").write_text("#!/bin/bash\necho hello\n")

        result = optimizer.optimize(skill_dir)
        assert isinstance(result, OptimizationResult)


class TestOptimizePromptBuilding:
    """Tests for prompt construction."""

    def test_prompt_includes_failing_checks(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test that the prompt includes failing check information."""
        report = optimizer._evaluate(valid_skill_path)
        content = (valid_skill_path / "SKILL.md").read_text()
        prompt = optimizer._build_prompt(content, report)

        # Should include failing check IDs
        for result in report.results:
            if not result.passed:
                assert result.check_id in prompt

    def test_prompt_includes_score(self, optimizer: SkillOptimizer, valid_skill_path: Path) -> None:
        """Test that the prompt includes the current score."""
        report = optimizer._evaluate(valid_skill_path)
        content = (valid_skill_path / "SKILL.md").read_text()
        prompt = optimizer._build_prompt(content, report)

        assert f"{report.quality_score}/100" in prompt

    def test_prompt_includes_fix_hints(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test that fix hints from failing checks are included."""
        report = optimizer._evaluate(valid_skill_path)
        content = (valid_skill_path / "SKILL.md").read_text()
        prompt = optimizer._build_prompt(content, report)

        # At least one failing check should have a fix hint
        has_fix = any(r.fix for r in report.results if not r.passed)
        if has_fix:
            assert "Fix:" in prompt

    def test_prompt_includes_skill_content(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test that the full SKILL.md content is in the prompt."""
        report = optimizer._evaluate(valid_skill_path)
        content = (valid_skill_path / "SKILL.md").read_text()
        prompt = optimizer._build_prompt(content, report)

        assert "--- Current SKILL.md ---" in prompt
        # Should contain at least the frontmatter delimiter
        assert "---\n" in prompt.split("--- Current SKILL.md ---")[1]

    def test_prompt_truncates_large_content(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test that very large SKILL.md content is truncated."""
        report = optimizer._evaluate(valid_skill_path)
        large_content = "---\nname: test\ndescription: test\n---\n" + "x" * (MAX_BODY_CHARS + 1000)
        prompt = optimizer._build_prompt(large_content, report)

        assert "[... content truncated ...]" in prompt


class TestParseResponse:
    """Tests for response parsing."""

    def test_parse_valid_response(self, optimizer: SkillOptimizer) -> None:
        """Test parsing a valid SKILL.md response."""
        result = optimizer._parse_response(OPTIMIZED_SKILL_MD)
        assert result.startswith("---")
        assert result.endswith("\n")

    def test_parse_strips_fences(self, optimizer: SkillOptimizer) -> None:
        """Test that wrapping markdown fences are stripped."""
        simple_md = "---\nname: test\ndescription: A skill\n---\n\nBody content\n"
        fenced = f"```yaml\n{simple_md}\n```"
        result = optimizer._parse_response(fenced)
        assert result.startswith("---")
        assert "```" not in result

    def test_parse_rejects_no_frontmatter(self, optimizer: SkillOptimizer) -> None:
        """Test that response without frontmatter is rejected."""
        with pytest.raises(GenerationError, match="does not start with frontmatter"):
            optimizer._parse_response("No frontmatter here")

    def test_parse_adds_trailing_newline(self, optimizer: SkillOptimizer) -> None:
        """Test that a trailing newline is added if missing."""
        content = "---\nname: test\n---\nBody"
        result = optimizer._parse_response(content)
        assert result.endswith("\n")


class TestBuildDiffText:
    """Tests for the _build_diff_text helper."""

    def test_removes_file_headers(self) -> None:
        raw = "--- SKILL.md (original)\n+++ SKILL.md (optimized)\n@@ -5,3 +5,4 @@\n context\n-old\n+new\n"
        result = _build_diff_text(raw).plain
        assert "---" not in result.split("\n")[0]
        assert "+++" not in result

    def test_skips_hunk_header(self) -> None:
        raw = "--- a\n+++ b\n@@ -5,3 +5,4 @@\n context\n-old\n+new\n"
        result = _build_diff_text(raw).plain
        assert "@@ " not in result
        assert "── Line" not in result

    def test_preserves_diff_lines_with_line_numbers(self) -> None:
        raw = "--- a\n+++ b\n@@ -5,3 +5,4 @@\n context\n-old line\n+new line\n"
        result = _build_diff_text(raw).plain
        assert "6 -old line" in result
        assert "6 +new line" in result

    def test_multi_hunk_line_numbers(self) -> None:
        raw = "--- a\n+++ b\n@@ -1,2 +1,2 @@\n-foo\n+bar\n@@ -10,2 +10,2 @@\n-baz\n+qux\n"
        result = _build_diff_text(raw).plain
        assert "1 -foo" in result
        assert "10 -baz" in result


def _seed_eval_history(skill_dir: Path) -> None:
    """Write a minimal eval history so optimize finds it."""
    report = EvaluationReport(
        skill_path=str(skill_dir),
        skill_name=skill_dir.name,
        timestamp="2026-03-31T10:00:00+00:00",
        duration_ms=10.0,
        quality_score=65.0,
        overall_pass=True,
        checks_run=37,
        checks_passed=30,
        checks_failed=7,
        results=[
            CheckResult(
                check_id="content.token-budget",
                check_name="Token Budget",
                passed=False,
                severity=Severity.MEDIUM,
                dimension=EvalDimension.CONTENT,
                message="Body exceeds token budget",
                fix="Reduce body content.",
            ),
        ],
        summary={},
    )
    save_eval(skill_dir, report)


class TestOptimizeCommand:
    """Tests for the CLI optimize command."""

    def test_missing_api_key(self, tmp_path: Path) -> None:
        """Test error when ANTHROPIC_API_KEY is not set."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: test\n---\n")
        _seed_eval_history(skill_dir)

        runner = CliRunner()
        result = runner.invoke(app, ["optimize", str(skill_dir)], env={"ANTHROPIC_API_KEY": ""})
        assert result.exit_code == 1
        assert "ANTHROPIC_API_KEY" in result.output

    def test_openai_model_checks_openai_key(self, tmp_path: Path) -> None:
        """Test that an OpenAI model checks OPENAI_API_KEY."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: test\n---\n")
        _seed_eval_history(skill_dir)

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["optimize", str(skill_dir), "--model", "gpt-4o"],
            env={"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""},
        )
        assert result.exit_code == 1
        assert "OPENAI_API_KEY" in result.output

    def test_nonexistent_path(self) -> None:
        """Test error for nonexistent path."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["optimize", "/nonexistent/path"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_no_skill_md(self, tmp_path: Path) -> None:
        """Test error when SKILL.md is missing."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(app, ["optimize", str(empty_dir)])
        assert result.exit_code == 1
        assert "No SKILL.md" in result.output

    def test_no_eval_history_exits_with_error(self, tmp_path: Path) -> None:
        """Test error when no eval history exists."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: test\n---\n")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["optimize", str(skill_dir)],
            env={"ANTHROPIC_API_KEY": "test-key"},
        )
        assert result.exit_code == 1
        assert "No evaluation results found" in result.output


# =============================================================================
# optimize_from_history tests
# =============================================================================


def _make_eval_record(
    score: float = 65.0,
    judge: JudgeResult | None = None,
) -> EvalRecord:
    """Build a minimal EvalRecord for testing."""
    results = [
        CheckResult(
            check_id="structure.skill-md-exists",
            check_name="SKILL.md Exists",
            passed=True,
            severity=Severity.HIGH,
            dimension=EvalDimension.STRUCTURE,
            message="SKILL.md found",
        ),
        CheckResult(
            check_id="content.token-budget",
            check_name="Token Budget",
            passed=False,
            severity=Severity.MEDIUM,
            dimension=EvalDimension.CONTENT,
            message="Body exceeds token budget",
            fix="Reduce body content.",
        ),
    ]
    report = EvaluationReport(
        skill_path="/tmp/test-skill",
        skill_name="test-skill",
        timestamp="2026-03-31T10:00:00+00:00",
        duration_ms=10.0,
        quality_score=score,
        overall_pass=True,
        checks_run=37,
        checks_passed=30,
        checks_failed=7,
        results=results,
        summary={},
    )
    return EvalRecord(
        schema_version="2.0",
        report=report,
        judge=judge,
        judge_model="claude-haiku-4-5-20251001" if judge else None,
        judge_usage=None,
    )


def _make_judge_result() -> JudgeResult:
    """Build a minimal JudgeResult for testing."""
    criteria = (
        JudgeCriterion(
            id="intent_clarity",
            name="Intent Clarity",
            axis="activation",
            score=2,
            reasoning="Description is vague.",
        ),
        JudgeCriterion(
            id="trigger_coverage",
            name="Trigger Coverage",
            axis="activation",
            score=1,
            reasoning="Missing implicit triggers.",
        ),
    )
    return JudgeResult(
        criteria=criteria,
        activation_score=37.5,
        instruction_score=50.0,
        judge_score=43.8,
        verdict="Poor",
        suggestions=("Broaden trigger phrases.", "Add error handling."),
    )


class TestOptimizeFromHistory:
    """Tests for optimize_from_history()."""

    def test_returns_result(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        record = _make_eval_record()
        result = optimizer.optimize_from_history(valid_skill_path, record)
        assert isinstance(result, OptimizationResult)
        assert result.original_content != ""
        assert result.optimized_content.startswith("---")

    def test_original_score_from_history(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        record = _make_eval_record(score=42.5)
        result = optimizer.optimize_from_history(valid_skill_path, record)
        assert result.original_score == 42.5

    def test_re_evaluate_runs_fresh(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        record = _make_eval_record()
        result = optimizer.optimize_from_history(valid_skill_path, record)
        # optimized_score comes from fresh StaticEvaluator, not from history
        assert isinstance(result.optimized_score, float)
        assert 0 <= result.optimized_score <= 100

    def test_missing_skill_md(
        self, optimizer: SkillOptimizer, tmp_path: Path
    ) -> None:
        empty_dir = tmp_path / "no-skill"
        empty_dir.mkdir()
        record = _make_eval_record()
        with pytest.raises(GenerationError, match="SKILL.md not found"):
            optimizer.optimize_from_history(empty_dir, record)


class TestBuildPromptFromHistory:
    """Tests for _build_prompt_from_history()."""

    def test_includes_failing_checks(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        record = _make_eval_record()
        content = (valid_skill_path / "SKILL.md").read_text()
        prompt = optimizer._build_prompt_from_history(content, record)
        assert "content.token-budget" in prompt
        assert "Fix: Reduce body content." in prompt

    def test_includes_judge_feedback(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        judge = _make_judge_result()
        record = _make_eval_record(judge=judge)
        content = (valid_skill_path / "SKILL.md").read_text()
        prompt = optimizer._build_prompt_from_history(content, record)
        assert "--- LLM Judge Feedback ---" in prompt
        assert "Intent Clarity" in prompt
        assert "Description is vague." in prompt
        assert "Broaden trigger phrases." in prompt

    def test_omits_judge_when_null(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        record = _make_eval_record(judge=None)
        content = (valid_skill_path / "SKILL.md").read_text()
        prompt = optimizer._build_prompt_from_history(content, record)
        assert "LLM Judge Feedback" not in prompt

    def test_includes_score_and_content(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        record = _make_eval_record(score=65.0)
        content = (valid_skill_path / "SKILL.md").read_text()
        prompt = optimizer._build_prompt_from_history(content, record)
        assert "65.0/100" in prompt
        assert "--- Current SKILL.md ---" in prompt


class TestIncrementPatch:
    """Tests for _increment_patch()."""

    def test_standard_semver(self) -> None:
        assert _increment_patch("0.2.0") == "0.2.1"

    def test_two_part_version(self) -> None:
        assert _increment_patch("1.0") == "1.1"

    def test_already_patched(self) -> None:
        assert _increment_patch("1.2.3") == "1.2.4"
