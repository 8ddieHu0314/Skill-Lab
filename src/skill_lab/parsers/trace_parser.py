"""Parse JSONL trace files into TraceEvent objects."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from skill_lab.core.models import TraceEvent


def parse_trace_file(trace_path: Path) -> list[TraceEvent]:
    """Parse a JSONL trace file into TraceEvent objects.

    Args:
        trace_path: Path to the JSONL trace file.

    Returns:
        List of TraceEvent objects.

    Raises:
        FileNotFoundError: If the trace file doesn't exist.
        ValueError: If the file contains invalid JSON.
    """
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_path}")

    events: list[TraceEvent] = []
    with open(trace_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                event = _parse_event(data)
                events.append(event)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_num}: {e}") from e

    return events


def iter_trace_file(trace_path: Path) -> Iterator[TraceEvent]:
    """Iterate over events in a JSONL trace file.

    This is more memory-efficient for large trace files.

    Args:
        trace_path: Path to the JSONL trace file.

    Yields:
        TraceEvent objects.

    Raises:
        FileNotFoundError: If the trace file doesn't exist.
        ValueError: If a line contains invalid JSON.
    """
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_path}")

    with open(trace_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                yield _parse_event(data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_num}: {e}") from e


def _parse_event(data: dict[str, Any]) -> TraceEvent:
    """Parse a single JSON object into a TraceEvent.

    Handles various trace formats (Codex, Claude, etc.) by normalizing
    to a common TraceEvent structure.

    Args:
        data: Dictionary from parsed JSON line.

    Returns:
        TraceEvent object.
    """
    # Extract common fields
    event_type = data.get("type", "unknown")
    item_type = None
    command = None
    output = None
    timestamp = None

    # Handle Codex-style traces
    if "item" in data:
        item = data["item"]
        item_type = item.get("type")
        if item_type == "function_call":
            # Function call with arguments
            command = item.get("name", "")
            args = item.get("arguments", "")
            if args:
                command = f"{command} {args}"
        elif item_type == "function_call_output":
            output = item.get("output", "")
        elif item_type == "command_execution":
            # Command execution with command at top level
            command = data.get("command")
            output = data.get("output")

    if command is None and "command" in data:
        # Direct command format
        item_type = "command_execution"
        command = data["command"]
        output = data.get("output")
    elif "name" in data and data.get("type") == "function_call":
        # Simplified function call format
        item_type = "command_execution"
        command = data.get("name", "")
        args = data.get("arguments", "")
        if args:
            command = f"{command} {args}"

    # Extract timestamp if available
    timestamp = data.get("timestamp") or data.get("time")

    return TraceEvent(
        type=event_type,
        item_type=item_type,
        command=command,
        output=output,
        timestamp=timestamp,
        raw=data,
    )
