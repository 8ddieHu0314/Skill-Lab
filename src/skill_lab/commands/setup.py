"""Setup and track-invocation commands."""

import contextlib
import json as json_module
import sys
from pathlib import Path

from skill_lab.cli import app, console
from skill_lab.core.telemetry import record_event


def _find_skill_md(skill_name: str, cwd: str) -> Path | None:
    """Search common locations for a skill's SKILL.md. Returns path if found."""
    if not skill_name or "/" in skill_name or "\\" in skill_name or skill_name.startswith("."):
        return None
    search_dirs = [
        Path.home() / ".claude" / "skills" / skill_name,
        Path.home() / ".cursor" / "skills" / skill_name,
    ]
    if cwd:
        search_dirs += [
            Path(cwd) / ".claude" / "skills" / skill_name,
            Path(cwd) / "skills" / skill_name,
        ]
    for skill_dir in search_dirs:
        if (skill_dir / "SKILL.md").exists():
            return skill_dir
    return None


@app.command("setup")
def setup() -> None:
    """Configure hooks for automatic skill invocation tracking.

    Writes PostToolUse hooks to Claude Code (~/.claude/settings.json) and
    Cursor (~/.cursor/hooks.json) so that sklab records a row in
    ~/.sklab/usage.db every time a skill fires. Safe to run multiple times.
    """
    from skill_lab.core.setup import run_setup

    console.print("[bold]Setting up sklab skill tracking hooks...[/bold]\n")
    results = run_setup()

    for tool, status in results.items():
        if status == "configured":
            console.print(f"  [green]\u2713[/green] {tool}: hook configured")
        elif status == "already_configured":
            console.print(f"  [dim]\u2013[/dim] {tool}: already configured")
        else:
            console.print(f"  [dim]\u2013[/dim] {tool}: {status.replace('_', ' ')}")

    newly_configured = [t for t, s in results.items() if s == "configured"]
    console.print()
    if newly_configured:
        console.print(
            "[green]Done![/green] Skill invocations will be tracked automatically.\n"
            "[dim]Run [bold]sklab stats[/bold] to view your usage.[/dim]"
        )
    else:
        console.print("[dim]No changes made.[/dim]")


@app.command("_track-invocation", hidden=True)
def track_invocation() -> None:
    """Record a skill invocation from a PostToolUse hook. Reads JSON from stdin."""
    from skill_lab.core.tokens import estimate_tokens

    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        data = json_module.loads(raw)
        skill_name: str = data.get("tool_input", {}).get("skill", "")
        if not skill_name:
            return
        cwd: str = data.get("cwd", "")
        skill_dir = _find_skill_md(skill_name, cwd)
        tokens: int | None = None
        skill_path_str: str | None = None
        if skill_dir is not None:
            skill_path_str = str(skill_dir)
            with contextlib.suppress(Exception):
                tokens = estimate_tokens((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
        record_event(
            command="skill-invoke",
            duration_ms=0,
            exit_code=0,
            skill_name=skill_name,
            input_tokens=tokens,
            skill_path=skill_path_str,
        )
    except Exception:
        pass  # Never let the hook crash
