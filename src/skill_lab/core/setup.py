"""Hook setup for automatic skill invocation tracking.

Writes PostToolUse hooks to Claude Code and Cursor settings files so that
sklab records a row in ~/.sklab/usage.db every time a skill fires.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Process-level cache so double-calling within a single CLI invocation is free.
_hooks_initialized: bool = False

_FIRST_RUN_NOTICE = (
    "sklab set up automatic skill tracking. Skill invocations are now recorded "
    "in ~/.sklab/usage.db for use with `sklab stats`.\n"
    "To disable: remove the 'sklab _track-invocation' hook from "
    "~/.claude/settings.json or ~/.cursor/hooks.json."
)

# User-scope settings files for each supported tool
_CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
_CURSOR_HOOKS = Path.home() / ".cursor" / "hooks.json"

_TRACK_CMD = "sklab _track-invocation"

# Claude Code: PostToolUse hook entry (matches the Skill tool)
_CLAUDE_HOOK_ENTRY: dict[str, object] = {
    "matcher": "Skill",
    "hooks": [
        {
            "type": "command",
            "command": _TRACK_CMD,
            "async": True,
            "timeout": 10,
        }
    ],
}

# Cursor: hook entry per Cursor hooks.json format
_CURSOR_HOOK_ENTRY: dict[str, object] = {
    "event": "PostToolUse",
    "matcher": "Skill",
    "command": _TRACK_CMD,
    "async": True,
}


def _read_json(path: Path) -> object:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _hook_already_present(hooks_list: list[object], command: str) -> bool:
    """Check if a hook with the given command string already exists in the list."""
    for entry in hooks_list:
        if not isinstance(entry, dict):
            continue
        # Claude Code format: entry has a nested "hooks" list
        for h in entry.get("hooks", []):  # type: ignore[union-attr]
            if isinstance(h, dict) and h.get("command") == command:
                return True
        # Cursor format: entry has "command" directly
        if entry.get("command") == command:
            return True
    return False


def setup_claude_code() -> str:
    """Configure the Claude Code PostToolUse hook.

    Returns one of: 'configured', 'already_configured', 'not_installed'.
    """
    if not _CLAUDE_SETTINGS.parent.exists():
        return "not_installed"

    raw = _read_json(_CLAUDE_SETTINGS)
    settings: dict[str, object] = raw if isinstance(raw, dict) else {}

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks

    post_tool_use: list[object] = hooks.get("PostToolUse", [])  # type: ignore[assignment]
    if not isinstance(post_tool_use, list):
        post_tool_use = []
    hooks["PostToolUse"] = post_tool_use

    if _hook_already_present(post_tool_use, _TRACK_CMD):
        return "already_configured"

    post_tool_use.append(_CLAUDE_HOOK_ENTRY)
    _write_json(_CLAUDE_SETTINGS, settings)
    return "configured"


def setup_cursor() -> str:
    """Configure the Cursor PostToolUse hook.

    Returns one of: 'configured', 'already_configured', 'not_installed'.
    """
    if not _CURSOR_HOOKS.parent.exists():
        return "not_installed"

    raw = _read_json(_CURSOR_HOOKS)
    hooks_list: list[object] = raw if isinstance(raw, list) else []

    if _hook_already_present(hooks_list, _TRACK_CMD):
        return "already_configured"

    hooks_list.append(_CURSOR_HOOK_ENTRY)
    _write_json(_CURSOR_HOOKS, hooks_list)
    return "configured"


def run_setup() -> dict[str, str]:
    """Run setup for all supported tools.

    Returns a dict mapping tool name to status string:
    'configured', 'already_configured', or 'not_installed'.
    """
    return {
        "Claude Code": setup_claude_code(),
        "Cursor": setup_cursor(),
    }


def _get_install_mtime() -> float | None:
    """Return the mtime of the installed skill-lab METADATA file.

    Used to detect reinstalls: if the package was installed more recently
    than we last recorded hooks_configured_at, it's a new install.
    Returns None if the mtime cannot be determined.
    """
    try:
        import importlib.metadata
        dist = importlib.metadata.distribution("skill-lab")
        meta = Path(str(dist.locate_file("METADATA")))
        return meta.stat().st_mtime
    except Exception:
        return None


def init_hooks_on_first_run() -> None:
    """Auto-configure hooks and show opt-out notice when appropriate.

    Shows the notice when:
    - The package was installed/reinstalled more recently than the last
      recorded hooks_configured_at timestamp (detected via METADATA mtime), or
    - A hook was newly written (e.g. user removed it manually).

    Silently skips in non-interactive environments (CI env var set, or
    stdout is not a TTY).
    """
    global _hooks_initialized
    if _hooks_initialized:
        return
    _hooks_initialized = True

    try:
        import time

        if os.environ.get("CI") or not sys.stdout.isatty():
            return

        from skill_lab.core.telemetry import _read_config, _write_config

        config = _read_config()
        install_mtime = _get_install_mtime()
        configured_at = float(config.get("hooks_configured_at", 0.0))

        # A reinstall is detected when the package METADATA is newer than
        # the last time we recorded successful hook configuration.
        is_new_install = install_mtime is not None and install_mtime > configured_at

        results = run_setup()
        any_configured = any(s == "configured" for s in results.values())
        any_installed = any(s != "not_installed" for s in results.values())

        # Show notice on reinstall (with any supported tool present) or when a
        # hook was newly written (e.g. user removed it and we re-added it).
        should_notify = any_configured or (is_new_install and any_installed)

        if should_notify:
            try:
                import typer
                typer.echo(_FIRST_RUN_NOTICE)
            except Exception:
                print(_FIRST_RUN_NOTICE)  # noqa: T201

        # Record this install's timestamp so future runs skip the notice
        # unless the package is reinstalled again.
        if is_new_install:
            config["hooks_configured_at"] = time.time()
            _write_config(config)

    except Exception:
        pass  # Never let first-run setup crash the CLI
