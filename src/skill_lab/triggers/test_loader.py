"""Load trigger test cases from YAML files.

Supports two formats:
1. Given/When/Then DSL (scenarios.yaml)
2. Simple flat format (triggers.yaml)
"""

from pathlib import Path
from typing import Any

import yaml

from skill_lab.core.models import TriggerExpectation, TriggerTestCase, TriggerType


def load_trigger_tests(skill_path: Path) -> tuple[list[TriggerTestCase], list[str]]:
    """Load trigger test cases from a skill directory.

    Looks for test definitions in:
    - tests/scenarios.yaml (Given/When/Then DSL)
    - tests/triggers.yaml (simple format)

    Args:
        skill_path: Path to the skill directory.

    Returns:
        Tuple of (test_cases, errors) where errors contains any parsing issues.
    """
    tests_dir = skill_path / "tests"
    test_cases: list[TriggerTestCase] = []
    errors: list[str] = []

    if not tests_dir.exists():
        return test_cases, ["No tests/ directory found"]

    # Try loading scenarios.yaml (Given/When/Then DSL)
    scenarios_path = tests_dir / "scenarios.yaml"
    if scenarios_path.exists():
        cases, errs = _load_scenarios_yaml(scenarios_path)
        test_cases.extend(cases)
        errors.extend(errs)

    # Try loading triggers.yaml (simple format)
    triggers_path = tests_dir / "triggers.yaml"
    if triggers_path.exists():
        cases, errs = _load_triggers_yaml(triggers_path)
        test_cases.extend(cases)
        errors.extend(errs)

    if not test_cases and not errors:
        errors.append("No test files found (scenarios.yaml or triggers.yaml)")

    return test_cases, errors


def _load_scenarios_yaml(path: Path) -> tuple[list[TriggerTestCase], list[str]]:
    """Load tests from Given/When/Then DSL format.

    Example format:
    ```yaml
    skill: my-skill
    scenarios:
      - name: "Direct skill invocation"
        given:
          - skill: my-skill
          - runtime: codex
        when:
          - prompt: "$my-skill do something"
          - trigger_type: explicit
        then:
          - skill_triggered: true
          - exit_code: 0
    ```
    """
    test_cases: list[TriggerTestCase] = []
    errors: list[str] = []

    try:
        content = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return [], [f"Failed to parse {path.name}: {e}"]

    if not content or not isinstance(content, dict):
        return [], [f"Invalid format in {path.name}: expected dict"]

    skill_name = content.get("skill", "unknown")
    scenarios = content.get("scenarios", [])

    if not isinstance(scenarios, list):
        return [], [f"Invalid scenarios in {path.name}: expected list"]

    for i, scenario in enumerate(scenarios):
        try:
            test_case = _parse_scenario(scenario, skill_name, i)
            test_cases.append(test_case)
        except (KeyError, ValueError) as e:
            errors.append(f"Error parsing scenario {i + 1} in {path.name}: {e}")

    return test_cases, errors


def _parse_scenario(
    scenario: dict[str, Any], default_skill: str, index: int
) -> TriggerTestCase:
    """Parse a single scenario from Given/When/Then format."""
    name = scenario.get("name", f"scenario-{index + 1}")
    scenario_id = scenario.get("id", f"scenario-{index + 1}")

    # Parse 'given' section
    given = _dict_from_list(scenario.get("given", []))
    skill_name = given.get("skill", default_skill)
    runtime = given.get("runtime")

    # Parse 'when' section
    when = _dict_from_list(scenario.get("when", []))
    prompt = when.get("prompt", "")
    trigger_type_str = when.get("trigger_type", "implicit")
    trigger_type = TriggerType(trigger_type_str)

    # Parse 'then' section
    then = _dict_from_list(scenario.get("then", []))
    expected = TriggerExpectation(
        skill_triggered=then.get("skill_triggered", True),
        exit_code=then.get("exit_code"),
        commands_include=tuple(then.get("commands_include", [])),
        files_created=tuple(then.get("files_created", [])),
        no_loops=then.get("no_loops", False),
    )

    return TriggerTestCase(
        id=scenario_id,
        name=name,
        skill_name=skill_name,
        prompt=prompt,
        trigger_type=trigger_type,
        expected=expected,
        runtime=runtime,
    )


def _dict_from_list(items: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
    """Convert a list of single-key dicts to one merged dict.

    Handles YAML like:
    given:
      - skill: my-skill
      - runtime: codex

    Converting to: {"skill": "my-skill", "runtime": "codex"}
    """
    if isinstance(items, dict):
        return items

    result: dict[str, Any] = {}
    for item in items:
        if isinstance(item, dict):
            result.update(item)
    return result


def _load_triggers_yaml(path: Path) -> tuple[list[TriggerTestCase], list[str]]:
    """Load tests from simple flat format.

    Example format:
    ```yaml
    skill: my-skill
    test_cases:
      - id: explicit-1
        type: explicit
        prompt: "$my-skill do something"
        expected: trigger
    ```
    """
    test_cases: list[TriggerTestCase] = []
    errors: list[str] = []

    try:
        content = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return [], [f"Failed to parse {path.name}: {e}"]

    if not content or not isinstance(content, dict):
        return [], [f"Invalid format in {path.name}: expected dict"]

    skill_name = content.get("skill", "unknown")
    cases = content.get("test_cases", [])

    if not isinstance(cases, list):
        return [], [f"Invalid test_cases in {path.name}: expected list"]

    for i, case in enumerate(cases):
        try:
            test_case = _parse_simple_case(case, skill_name, i)
            test_cases.append(test_case)
        except (KeyError, ValueError) as e:
            errors.append(f"Error parsing test case {i + 1} in {path.name}: {e}")

    return test_cases, errors


def _parse_simple_case(
    case: dict[str, Any], default_skill: str, index: int
) -> TriggerTestCase:
    """Parse a single test case from simple format."""
    case_id = case.get("id", f"test-{index + 1}")
    name = case.get("name", case_id)

    trigger_type_str = case.get("type", "implicit")
    trigger_type = TriggerType(trigger_type_str)

    prompt = case.get("prompt", "")

    # Simple format uses "expected: trigger" or "expected: no_trigger"
    expected_str = case.get("expected", "trigger")
    skill_triggered = expected_str != "no_trigger"

    expected = TriggerExpectation(
        skill_triggered=skill_triggered,
        exit_code=case.get("exit_code"),
        commands_include=tuple(case.get("commands_include", [])),
        files_created=tuple(case.get("files_created", [])),
        no_loops=case.get("no_loops", False),
    )

    return TriggerTestCase(
        id=case_id,
        name=name,
        skill_name=case.get("skill", default_skill),
        prompt=prompt,
        trigger_type=trigger_type,
        expected=expected,
        runtime=case.get("runtime"),
    )
