"""Shared constants for the skill-lab framework."""

from pathlib import Path

# Directory paths for .skill-lab artifacts
SKILLLAB_DIR = ".skill-lab"

# ~/.sklab home directory and config paths
SKLAB_HOME = Path.home() / ".sklab"
SKLAB_CONFIG = SKLAB_HOME / "config.json"
SKLAB_DB = SKLAB_HOME / "usage.db"
TESTS_DIR = ".skill-lab/tests"
TRACES_DIR = ".skill-lab/traces"


def skill_script_patterns(skill_name: str) -> list[str]:
    """Build patterns that indicate skill script execution.

    Used by runtime adapters (real-time detection) and TraceAnalyzer
    (post-hoc analysis) to identify when a skill's scripts are being run.

    Args:
        skill_name: Name of the skill to build patterns for.

    Returns:
        List of substring patterns to match against commands/paths.
    """
    return [
        f"scripts/{skill_name}",
        f"/{skill_name}/scripts/",
        f"skills/{skill_name}",
    ]
