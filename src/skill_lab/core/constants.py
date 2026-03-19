"""Shared constants for the skill-lab framework."""

from pathlib import Path

# Directory paths for .sklab project artifacts
SKILLLAB_DIR = ".sklab"

# ~/.sklab home directory and config paths
SKLAB_HOME = Path.home() / ".sklab"
SKLAB_CONFIG = SKLAB_HOME / "config.json"
SKLAB_DB = SKLAB_HOME / "usage.db"
SKLAB_INITIALIZED = SKLAB_HOME / ".initialized"
TESTS_DIR = ".sklab/tests"
TRACES_DIR = ".sklab/traces"


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
