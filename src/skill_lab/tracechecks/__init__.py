"""Trace analysis checks package.

This package provides YAML-driven configurable trace checks that validate
execution traces against user-defined expectations.
"""

from skill_lab.tracechecks.registry import TraceCheckRegistry, trace_registry
from skill_lab.tracechecks.trace_check_loader import load_trace_checks

__all__ = [
    "TraceCheckRegistry",
    "trace_registry",
    "load_trace_checks",
]
