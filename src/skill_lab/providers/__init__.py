"""Execution providers for trigger testing.

Providers control WHERE an agent runs (temp dir, Docker container),
while RuntimeAdapters control HOW we talk to the agent CLI.
"""

from skill_lab.providers.base import ExecutionContext, ExecutionProvider
from skill_lab.providers.docker import DockerProvider
from skill_lab.providers.local import LocalProvider

__all__ = ["DockerProvider", "ExecutionContext", "ExecutionProvider", "LocalProvider"]
