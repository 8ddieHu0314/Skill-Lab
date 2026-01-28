"""Runtime adapters for executing skills and capturing traces.

This module provides adapters for different agent runtimes (Codex, Claude)
that can execute skills and capture execution traces for analysis.
"""

from skill_lab.runtimes.base import RuntimeAdapter
from skill_lab.runtimes.claude_runtime import ClaudeRuntime
from skill_lab.runtimes.codex_runtime import CodexRuntime

__all__ = ["RuntimeAdapter", "CodexRuntime", "ClaudeRuntime"]
