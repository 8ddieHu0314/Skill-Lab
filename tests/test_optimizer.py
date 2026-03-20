"""Unit tests for LLM-powered SKILL.md optimization."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skill_lab.core.exceptions import GenerationError
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


def _mock_anthropic_response(text: str) -> MagicMock:
    """Create a mock Anthropic API response."""
    block = MagicMock()
    block.text = text
    message = MagicMock()
    message.content = [block]
    message.stop_reason = "end_turn"
    message.usage = MagicMock()
    message.usage.input_tokens = 500
    message.usage.output_tokens = 300
    return message


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock Anthropic client."""
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response(OPTIMIZED_SKILL_MD)
    return client


@pytest.fixture
def optimizer(mock_client: MagicMock) -> SkillOptimizer:
    """Create a SkillOptimizer with a mocked client."""
    pytest.importorskip("anthropic")
    with patch("anthropic.Anthropic", return_value=mock_client):
        opt = SkillOptimizer(api_key="test-key")
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

    def test_optimize_tracks_usage(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test that token usage is tracked after optimization."""
        result = optimizer.optimize(valid_skill_path)

        assert result.usage is not None
        assert result.usage.input_tokens == 500
        assert result.usage.output_tokens == 300
        assert result.usage.total_tokens == 800

    def test_optimize_missing_skill_md(
        self, optimizer: SkillOptimizer, tmp_path: Path
    ) -> None:
        """Test error when SKILL.md doesn't exist."""
        empty_dir = tmp_path / "no-skill"
        empty_dir.mkdir()

        with pytest.raises(GenerationError, match="SKILL.md not found"):
            optimizer.optimize(empty_dir)

    def test_optimize_handles_api_error(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test error handling when API call fails."""
        optimizer._client.messages.create.side_effect = Exception("Connection error")

        with pytest.raises(GenerationError, match="API call failed"):
            optimizer.optimize(valid_skill_path)

    def test_optimize_handles_empty_response(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test error handling for empty API response."""
        empty_msg = MagicMock()
        empty_msg.content = []
        empty_msg.stop_reason = "end_turn"
        empty_msg.usage = MagicMock()
        empty_msg.usage.input_tokens = 100
        empty_msg.usage.output_tokens = 0
        optimizer._client.messages.create.return_value = empty_msg

        with pytest.raises(GenerationError, match="empty response"):
            optimizer.optimize(valid_skill_path)

    def test_optimize_raises_on_max_tokens(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test error raised when model output is truncated by max_tokens limit."""
        truncated_msg = MagicMock()
        truncated_msg.stop_reason = "max_tokens"
        truncated_msg.usage = MagicMock()
        truncated_msg.usage.input_tokens = 500
        truncated_msg.usage.output_tokens = 8192
        optimizer._client.messages.create.return_value = truncated_msg

        with pytest.raises(GenerationError, match="truncated"):
            optimizer.optimize(valid_skill_path)

    def test_optimize_strips_markdown_fences(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test that markdown code fences are stripped from response."""
        fenced = f"```yaml\n{OPTIMIZED_SKILL_MD}\n```"
        optimizer._client.messages.create.return_value = _mock_anthropic_response(
            fenced
        )

        result = optimizer.optimize(valid_skill_path)
        assert not result.optimized_content.startswith("```")
        assert result.optimized_content.startswith("---")

    def test_optimize_rejects_invalid_response(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
        """Test error when response doesn't look like SKILL.md."""
        optimizer._client.messages.create.return_value = _mock_anthropic_response(
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

    def test_prompt_includes_score(
        self, optimizer: SkillOptimizer, valid_skill_path: Path
    ) -> None:
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
        large_content = "---\nname: test\ndescription: test\n---\n" + "x" * (
            MAX_BODY_CHARS + 1000
        )
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


class TestOptimizeCommand:
    """Tests for the CLI optimize command."""

    def test_missing_api_key(self, tmp_path: Path) -> None:
        """Test error when ANTHROPIC_API_KEY is not set."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\n"
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["optimize", str(skill_dir)], env={"ANTHROPIC_API_KEY": ""}
        )
        assert result.exit_code == 1
        assert "ANTHROPIC_API_KEY" in result.output

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
