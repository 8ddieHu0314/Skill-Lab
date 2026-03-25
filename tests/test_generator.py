"""Unit tests for LLM-based trigger test generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from skill_lab.core.exceptions import GenerationError
from skill_lab.core.llm import LLMResponse
from skill_lab.triggers.generator import (
    DEFAULT_MODEL,
    MAX_BODY_CHARS,
    TriggerGenerator,
)

# Sample valid YAML that a model might return
VALID_YAML_RESPONSE = """\
skill: my-skill

test_cases:
  - id: explicit-1
    name: "Direct invocation"
    type: explicit
    prompt: "$my-skill do something"
    expected: trigger

  - id: explicit-2
    name: "Invoke with action"
    type: explicit
    prompt: "$my-skill run tests"
    expected: trigger

  - id: implicit-1
    name: "Describe the scenario"
    type: implicit
    prompt: "I need to do something for my project"
    expected: trigger

  - id: implicit-2
    name: "Ask for help"
    type: implicit
    prompt: "Can you help me with this task?"
    expected: trigger

  - id: contextual-1
    name: "Realistic prompt with noise"
    type: contextual
    prompt: "Working on a big project, I need to do something for the report"
    expected: trigger

  - id: contextual-2
    name: "Domain context prompt"
    type: contextual
    prompt: "I'm preparing for a meeting and need to do this thing"
    expected: trigger

  - id: negative-1
    name: "Unrelated request"
    type: negative
    prompt: "How do I fix this CSS issue?"
    expected: no_trigger

  - id: negative-2
    name: "Similar domain but different"
    type: negative
    prompt: "Delete the old files"
    expected: no_trigger

  - id: negative-3
    name: "Informational question"
    type: negative
    prompt: "What tools are available?"
    expected: no_trigger
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
    provider.create_message.return_value = _mock_llm_response(VALID_YAML_RESPONSE)
    return provider


@pytest.fixture
def generator(mock_provider: MagicMock) -> TriggerGenerator:
    """Create a TriggerGenerator with a mocked provider."""
    gen = TriggerGenerator(provider=mock_provider)
    return gen


class TestTriggerGenerator:
    """Tests for the TriggerGenerator class."""

    def test_generate_returns_valid_yaml(
        self, generator: TriggerGenerator, fixtures_dir: Path
    ) -> None:
        """Test that generate() returns parseable YAML."""
        skill_path = fixtures_dir / "skills" / "creating-reports"
        result = generator.generate(skill_path)

        data = yaml.safe_load(result)
        assert isinstance(data, dict)
        assert "skill" in data
        assert "test_cases" in data

    def test_generate_forces_correct_skill_name(
        self, generator: TriggerGenerator, fixtures_dir: Path
    ) -> None:
        """Test that the skill name is forced to match the actual skill."""
        skill_path = fixtures_dir / "skills" / "creating-reports"
        result = generator.generate(skill_path)

        data = yaml.safe_load(result)
        assert data["skill"] == "creating-reports"

    def test_generate_all_four_types(self, generator: TriggerGenerator, fixtures_dir: Path) -> None:
        """Test that all 4 trigger types are present."""
        skill_path = fixtures_dir / "skills" / "creating-reports"
        result = generator.generate(skill_path)

        data = yaml.safe_load(result)
        types = {tc["type"] for tc in data["test_cases"]}
        assert "explicit" in types
        assert "implicit" in types
        assert "contextual" in types
        assert "negative" in types

    def test_generate_and_write_creates_file(
        self, generator: TriggerGenerator, tmp_path: Path
    ) -> None:
        """Test that generate_and_write() creates the output file."""
        # Set up a minimal skill directory
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill\n---\n\nBody content"
        )

        result_path = generator.generate_and_write(skill_dir)

        assert result_path.exists()
        assert result_path == skill_dir / ".sklab" / "tests" / "triggers.yaml"
        data = yaml.safe_load(result_path.read_text())
        assert data["skill"] == "my-skill"

    def test_generate_and_write_raises_on_existing(
        self, generator: TriggerGenerator, tmp_path: Path
    ) -> None:
        """Test that generate_and_write() raises FileExistsError if not forced."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill\n---\n\nBody"
        )
        # Create existing file
        output_dir = skill_dir / ".sklab" / "tests"
        output_dir.mkdir(parents=True)
        (output_dir / "triggers.yaml").write_text("existing content")

        with pytest.raises(FileExistsError, match="Use --force to overwrite"):
            generator.generate_and_write(skill_dir)

    def test_generate_and_write_force_overwrites(
        self, generator: TriggerGenerator, tmp_path: Path
    ) -> None:
        """Test that generate_and_write() overwrites with force=True."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill\n---\n\nBody"
        )
        # Create existing file
        output_dir = skill_dir / ".sklab" / "tests"
        output_dir.mkdir(parents=True)
        (output_dir / "triggers.yaml").write_text("existing content")

        result_path = generator.generate_and_write(skill_dir, force=True)
        assert result_path.exists()
        content = result_path.read_text()
        assert "existing content" not in content

    def test_generate_handles_malformed_yaml(
        self, generator: TriggerGenerator, mock_provider: MagicMock, fixtures_dir: Path
    ) -> None:
        """Test error handling for malformed YAML response."""
        mock_provider.create_message.return_value = _mock_llm_response(
            "this: is: not: valid: yaml:\n  - [broken"
        )
        skill_path = fixtures_dir / "skills" / "creating-reports"

        with pytest.raises(GenerationError, match="Failed to parse generated YAML"):
            generator.generate(skill_path)

    def test_generate_strips_markdown_fences(
        self, generator: TriggerGenerator, mock_provider: MagicMock, fixtures_dir: Path
    ) -> None:
        """Test that markdown code fences are stripped from response."""
        fenced = f"```yaml\n{VALID_YAML_RESPONSE}\n```"
        mock_provider.create_message.return_value = _mock_llm_response(fenced)

        skill_path = fixtures_dir / "skills" / "creating-reports"
        result = generator.generate(skill_path)

        data = yaml.safe_load(result)
        assert "test_cases" in data

    def test_generate_parse_error(self, generator: TriggerGenerator, tmp_path: Path) -> None:
        """Test error when skill can't be parsed."""
        skill_dir = tmp_path / "broken-skill"
        skill_dir.mkdir()
        # No SKILL.md — will produce parse error

        with pytest.raises(GenerationError, match="Failed to parse skill"):
            generator.generate(skill_dir)

    def test_generate_tracks_usage(
        self, generator: TriggerGenerator, fixtures_dir: Path
    ) -> None:
        """Test that token usage is tracked after generation."""
        skill_path = fixtures_dir / "skills" / "creating-reports"
        generator.generate(skill_path)

        assert generator.last_usage is not None
        assert generator.last_usage.input_tokens == 500
        assert generator.last_usage.output_tokens == 300


class TestPromptBuilding:
    """Tests for prompt construction."""

    def test_prompt_includes_skill_name(self, generator: TriggerGenerator) -> None:
        """Test that the prompt includes the skill name."""
        prompt = generator._build_prompt("my-skill", "A description", "Body content")
        assert "my-skill" in prompt
        assert "A description" in prompt

    def test_prompt_truncates_long_body(self, generator: TriggerGenerator) -> None:
        """Test that long body content is truncated."""
        long_body = "x" * (MAX_BODY_CHARS + 1000)
        prompt = generator._build_prompt("skill", "desc", long_body)

        assert "[... content truncated ...]" in prompt
        # Should not contain the full body
        assert len(prompt) < len(long_body)

    def test_prompt_preserves_short_body(self, generator: TriggerGenerator) -> None:
        """Test that short body content is preserved fully."""
        short_body = "Short body content"
        prompt = generator._build_prompt("skill", "desc", short_body)

        assert short_body in prompt
        assert "[... content truncated ...]" not in prompt


class TestYamlValidation:
    """Tests for YAML structure validation."""

    def test_missing_test_cases_key(self, generator: TriggerGenerator) -> None:
        """Test validation catches missing test_cases."""
        with pytest.raises(GenerationError, match="missing 'test_cases' key"):
            generator._parse_response("skill: test\nother_key: value", "test")

    def test_empty_test_cases(self, generator: TriggerGenerator) -> None:
        """Test validation catches empty test_cases list."""
        with pytest.raises(GenerationError, match="empty or invalid"):
            generator._parse_response("skill: test\ntest_cases: []", "test")

    def test_invalid_type(self, generator: TriggerGenerator) -> None:
        """Test validation catches invalid trigger type."""
        yaml_str = (
            "skill: test\ntest_cases:\n"
            "  - id: t1\n    type: invalid\n    prompt: hi\n    expected: trigger"
        )
        with pytest.raises(GenerationError, match="invalid type 'invalid'"):
            generator._parse_response(yaml_str, "test")

    def test_invalid_expected(self, generator: TriggerGenerator) -> None:
        """Test validation catches invalid expected value."""
        yaml_str = (
            "skill: test\ntest_cases:\n"
            "  - id: t1\n    type: explicit\n    prompt: hi\n    expected: maybe"
        )
        with pytest.raises(GenerationError, match="invalid expected 'maybe'"):
            generator._parse_response(yaml_str, "test")

    def test_missing_required_field(self, generator: TriggerGenerator) -> None:
        """Test validation catches missing required fields."""
        yaml_str = "skill: test\ntest_cases:\n  - id: t1\n    type: explicit\n    prompt: hi"
        with pytest.raises(GenerationError, match="missing required field 'expected'"):
            generator._parse_response(yaml_str, "test")


class TestGenerateCommand:
    """Tests for the CLI generate command."""

    def test_missing_api_key(self, tmp_path: Path) -> None:
        """Test error when API key is not set."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: test\n---\n")

        runner = CliRunner()
        result = runner.invoke(app, ["generate", str(skill_dir)], env={"ANTHROPIC_API_KEY": ""})
        assert result.exit_code == 1
        assert "ANTHROPIC_API_KEY" in result.output

    def test_openai_model_checks_openai_key(self, tmp_path: Path) -> None:
        """Test that an OpenAI model checks OPENAI_API_KEY."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: test\n---\n")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["generate", str(skill_dir), "--model", "gpt-4o-mini"],
            env={"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""},
        )
        assert result.exit_code == 1
        assert "OPENAI_API_KEY" in result.output

    def test_gemini_model_checks_gemini_key(self, tmp_path: Path) -> None:
        """Test that a Gemini model checks GEMINI_API_KEY."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: test\n---\n")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["generate", str(skill_dir), "--model", "gemini-2.5-flash"],
            env={"GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": ""},
        )
        assert result.exit_code == 1
        assert "GEMINI_API_KEY" in result.output

    def test_nonexistent_path(self) -> None:
        """Test error for nonexistent path."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["generate", "/nonexistent/path"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_no_skill_md(self, tmp_path: Path) -> None:
        """Test error when SKILL.md is missing."""
        from typer.testing import CliRunner

        from skill_lab.cli import app

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(app, ["generate", str(empty_dir)])
        assert result.exit_code == 1
        assert "No SKILL.md" in result.output
