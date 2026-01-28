"""Load trace check definitions from YAML."""

from pathlib import Path
from typing import Any

import yaml

from skill_lab.core.models import TraceCheckDefinition


def load_trace_checks(skill_path: Path) -> list[TraceCheckDefinition]:
    """Load trace check definitions from a skill's tests/trace_checks.yaml.

    Args:
        skill_path: Path to the skill directory.

    Returns:
        List of TraceCheckDefinition objects.

    Raises:
        FileNotFoundError: If trace_checks.yaml doesn't exist.
        ValueError: If the YAML is malformed or checks are invalid.
    """
    yaml_path = skill_path / "tests" / "trace_checks.yaml"

    if not yaml_path.exists():
        raise FileNotFoundError(f"Trace checks file not found: {yaml_path}")

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"Empty trace checks file: {yaml_path}")

    checks_data = data.get("checks", [])
    if not checks_data:
        raise ValueError(f"No checks defined in: {yaml_path}")

    return [_parse_check(check_data, yaml_path) for check_data in checks_data]


def _parse_check(data: dict[str, Any], source_path: Path) -> TraceCheckDefinition:
    """Parse a single check definition from YAML data.

    Args:
        data: Dictionary containing check definition.
        source_path: Path to the source YAML file (for error messages).

    Returns:
        TraceCheckDefinition object.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    # Required fields
    check_id = data.get("id")
    if not check_id:
        raise ValueError(f"Check missing required 'id' field in {source_path}")

    check_type = data.get("type")
    if not check_type:
        raise ValueError(f"Check '{check_id}' missing required 'type' field in {source_path}")

    # Validate check type
    valid_types = {"command_presence", "file_creation", "event_sequence", "loop_detection", "efficiency"}
    if check_type not in valid_types:
        raise ValueError(
            f"Check '{check_id}' has invalid type '{check_type}'. "
            f"Valid types: {', '.join(sorted(valid_types))}"
        )

    # Parse type-specific fields
    sequence = data.get("sequence", [])
    if isinstance(sequence, list):
        sequence = tuple(sequence)

    return TraceCheckDefinition(
        id=check_id,
        type=check_type,
        description=data.get("description"),
        pattern=data.get("pattern"),
        path=data.get("path"),
        sequence=sequence,
        max_retries=data.get("max_retries", 3),
        max_commands=data.get("max_commands"),
    )
