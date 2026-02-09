"""LLM-based trigger test case generator.

Uses the Anthropic SDK to read a SKILL.md and generate trigger test cases
with ~13 tests across all 4 types (explicit, implicit, contextual, negative).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from skill_lab.core.exceptions import GenerationError
from skill_lab.parsers.skill_parser import parse_skill

_SKILL_PROMPT_PATH = Path(__file__).parent / "generate_triggers_skill.md"

SYSTEM_PROMPT = (
    "You are executing the generate-triggers skill. "
    "Follow the instructions below to generate trigger test cases for the target skill. "
    "Output ONLY valid YAML with no markdown fences, no explanations, no commentary.\n\n"
    + _SKILL_PROMPT_PATH.read_text(encoding="utf-8")
)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_BODY_CHARS = 4000

VALID_TYPES = {"explicit", "implicit", "contextual", "negative"}
VALID_EXPECTED = {"trigger", "no_trigger"}


class GenerationUsage:
    """Token usage and cost from a generation API call."""

    # Pricing per million tokens (input, output) — updated 2025-02
    _PRICING: dict[str, tuple[float, float]] = {
        "claude-haiku-4-5-20251001": (0.80, 4.00),
        "claude-sonnet-4-5-20250929": (3.00, 15.00),
        "claude-opus-4-6": (15.00, 75.00),
    }

    def __init__(self, input_tokens: int, output_tokens: int, model: str) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def input_cost(self) -> float | None:
        """Input cost in USD, or None if model pricing is unknown."""
        pricing = self._PRICING.get(self.model)
        if pricing is None:
            return None
        return self.input_tokens * pricing[0] / 1_000_000

    @property
    def output_cost(self) -> float | None:
        """Output cost in USD, or None if model pricing is unknown."""
        pricing = self._PRICING.get(self.model)
        if pricing is None:
            return None
        return self.output_tokens * pricing[1] / 1_000_000

    @property
    def total_cost(self) -> float | None:
        """Total cost in USD, or None if model pricing is unknown."""
        input_c = self.input_cost
        output_c = self.output_cost
        if input_c is None or output_c is None:
            return None
        return input_c + output_c


class TriggerGenerator:
    """Generates trigger test cases for a skill using the Anthropic API."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
    ) -> None:
        """Initialize the generator.

        Args:
            model: Anthropic model ID to use for generation.
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
        """
        import anthropic  # lazy import — anthropic is optional

        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)
        self.last_usage: GenerationUsage | None = None

    def generate(self, skill_path: Path) -> str:
        """Generate trigger test YAML for a skill.

        Args:
            skill_path: Path to the skill directory (must contain SKILL.md).

        Returns:
            Generated YAML string.

        Raises:
            GenerationError: If generation fails.
        """
        skill = parse_skill(skill_path)
        if skill.parse_errors:
            raise GenerationError(
                f"Failed to parse skill: {'; '.join(skill.parse_errors)}",
                skill_path=str(skill_path),
            )

        skill_name = skill.metadata.name if skill.metadata else skill_path.name
        description = skill.metadata.description if skill.metadata else ""
        body = skill.body

        prompt = self._build_prompt(skill_name, description, body)
        response_text = self._call_api(prompt)
        data = self._parse_response(response_text, skill_name)

        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def generate_and_write(self, skill_path: Path, *, force: bool = False) -> Path:
        """Generate trigger tests and write to .skill-lab/tests/triggers.yaml.

        Args:
            skill_path: Path to the skill directory.
            force: If True, overwrite existing file.

        Returns:
            Path to the written file.

        Raises:
            FileExistsError: If file exists and force is False.
            GenerationError: If generation fails.
        """
        output_dir = skill_path / ".skill-lab" / "tests"
        output_path = output_dir / "triggers.yaml"

        if output_path.exists() and not force:
            raise FileExistsError(
                f"Trigger tests already exist at {output_path}. Use --force to overwrite."
            )

        yaml_content = self.generate(skill_path)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_content, encoding="utf-8")
        return output_path

    def _build_prompt(self, skill_name: str, description: str, body: str) -> str:
        """Build the user message for the API call.

        Args:
            skill_name: Name of the skill.
            description: Skill description from frontmatter.
            body: Skill body content (markdown after frontmatter).

        Returns:
            Formatted user message.
        """
        truncated_body = body[:MAX_BODY_CHARS]
        if len(body) > MAX_BODY_CHARS:
            truncated_body += "\n\n[... content truncated ...]"

        return (
            f"Generate trigger test cases for this skill:\n\n"
            f"Skill Name: {skill_name}\n"
            f"Description: {description}\n\n"
            f"--- SKILL.md content ---\n"
            f"{truncated_body}"
        )

    def _call_api(self, prompt: str) -> str:
        """Call the Anthropic API to generate test cases.

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
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
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

    def _parse_response(self, response_text: str, skill_name: str) -> dict[str, Any]:
        """Parse and validate the API response.

        Strips markdown fences if present, parses YAML, validates structure,
        and forces the correct skill name.

        Args:
            response_text: Raw response text from the API.
            skill_name: Expected skill name (will be forced into output).

        Returns:
            Validated YAML data dictionary.

        Raises:
            GenerationError: If response is invalid YAML or wrong structure.
        """
        # Strip markdown code fences if present
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```yaml or ```)
            lines = lines[1:]
            # Remove last line if it's closing fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise GenerationError(
                f"Failed to parse generated YAML: {e}",
                suggestion="The model returned invalid YAML. Try running again.",
            ) from e

        if not isinstance(data, dict):
            raise GenerationError(
                f"Expected YAML mapping, got {type(data).__name__}",
                suggestion="The model returned unexpected format. Try running again.",
            )

        self._validate_yaml_structure(data)

        # Force correct skill name
        data["skill"] = skill_name

        return data

    def _validate_yaml_structure(self, data: dict[str, Any]) -> None:
        """Validate the structure of generated YAML.

        Args:
            data: Parsed YAML dictionary.

        Raises:
            GenerationError: If required keys are missing or values are invalid.
        """
        if "test_cases" not in data:
            raise GenerationError(
                "Generated YAML missing 'test_cases' key",
                suggestion="The model returned incomplete output. Try running again.",
            )

        test_cases = data["test_cases"]
        if not isinstance(test_cases, list) or len(test_cases) == 0:
            raise GenerationError(
                "Generated YAML has empty or invalid 'test_cases'",
                suggestion="The model returned no test cases. Try running again.",
            )

        for i, case in enumerate(test_cases):
            if not isinstance(case, dict):
                raise GenerationError(f"Test case {i + 1} is not a mapping")

            for required in ("id", "type", "prompt", "expected"):
                if required not in case:
                    raise GenerationError(f"Test case {i + 1} missing required field '{required}'")

            case_type = case.get("type")
            if case_type not in VALID_TYPES:
                raise GenerationError(
                    f"Test case {i + 1} has invalid type '{case_type}', "
                    f"expected one of: {', '.join(sorted(VALID_TYPES))}"
                )

            expected = case.get("expected")
            if expected not in VALID_EXPECTED:
                raise GenerationError(
                    f"Test case {i + 1} has invalid expected '{expected}', "
                    f"expected one of: {', '.join(sorted(VALID_EXPECTED))}"
                )
