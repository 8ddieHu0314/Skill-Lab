"""CLI interface for skill-lab."""

import contextlib
import functools
import sys
import time
from collections.abc import Callable, Iterator
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from skill_lab import __version__
from skill_lab.core.constants import SKLAB_HOME, SKLAB_INITIALIZED
from skill_lab.core.telemetry import (
    _pop_pending_error,
    _pop_telemetry_extras,
    _store_pending_error,
    check_for_update,
    init_telemetry,
    push_telemetry_extra,
    record_error,
    record_event,
)

app = typer.Typer(
    name="sklab",
    help="Agent Skills Evaluation Framework",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"sklab {__version__}")
        raise typer.Exit()


def _maybe_first_run_scan() -> bool:
    """Return True if the first-run scan was executed, False if already initialized."""
    """On first ever `sklab` invocation, scan for skills and show a welcome evaluation.

    Discovery order:
      1. Git repo root (if inside a repo)
      2. ~/.claude/.skill/ (Claude-installed skills)
      3. Current working directory (fallback)

    Writes ~/.sklab/.initialized so this only runs once.
    """
    if SKLAB_INITIALIZED.exists():
        return False

    # Mark as initialized immediately so a crash mid-scan doesn't loop forever
    SKLAB_HOME.mkdir(parents=True, exist_ok=True)
    SKLAB_INITIALIZED.touch()

    # Discover roots in priority order, deduplicating
    cwd = Path.cwd()
    roots: list[Path] = []
    seen: set[Path] = set()

    repo_root = _find_repo_root(cwd)
    if repo_root and repo_root not in seen:
        roots.append(repo_root)
        seen.add(repo_root)

    claude_skills = Path.home() / ".claude" / ".skill"
    if claude_skills.exists() and claude_skills not in seen:
        roots.append(claude_skills)
        seen.add(claude_skills)

    if cwd not in seen:
        roots.append(cwd)
        seen.add(cwd)

    # Collect all skill paths across all roots
    skill_paths: list[Path] = []
    for root in roots:
        skill_paths.extend(_discover_skills(root))

    # Welcome banner
    console.print()
    console.print(
        Panel(
            "[bold]Welcome to sklab![/bold]\n\n"
            "Scanning for skills across your repo and installed skills...",
            expand=False,
            border_style="cyan",
        )
    )
    console.print()

    if not skill_paths:
        console.print("[yellow]No skills found in your repo or installed skills.[/yellow]")
        console.print()
        _print_getting_started()
        return True

    console.print(f"[dim]Found {len(skill_paths)} skill(s). Running initial evaluation...[/dim]\n")

    from skill_lab.evaluators.static_evaluator import StaticEvaluator
    from skill_lab.reporters.console_reporter import ConsoleReporter

    evaluator = StaticEvaluator()
    summary_rows: list[tuple[str, str, str, str]] = []

    for sp in skill_paths:
        try:
            report = evaluator.evaluate(sp)
        except Exception as e:
            console.print(f"[red]Error evaluating {sp.name}: {e}[/red]")
            continue

        ConsoleReporter(verbose=False).report(report)

        score_str = f"{report.quality_score:.1f}"
        status_str = "[green]PASS[/green]" if report.overall_pass else "[red]FAIL[/red]"
        skill_name = report.skill_name or sp.name
        try:
            rel_path = str(sp.relative_to(cwd))
        except ValueError:
            rel_path = str(sp)
        summary_rows.append((skill_name, rel_path, score_str, status_str))

    # Summary table
    console.print()
    table = Table(title=f"Initial Scan — {len(skill_paths)} skill(s)", box=box.ROUNDED)
    table.add_column("Skill", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Status", justify="center")
    for name, path, score, status in summary_rows:
        table.add_row(name, path, score, status)
    console.print(table)
    console.print()

    _print_getting_started()
    return True


def _print_getting_started() -> None:
    """Print a command reference guide. Shown after first-run scan and on every bare `sklab`."""
    guide = Table.grid(padding=(0, 2))
    guide.add_column(style="bold cyan", no_wrap=True)
    guide.add_column(style="dim")

    guide.add_row(
        "sklab evaluate [green]./my-skill[/green]", "Full quality evaluation (0–100 score)"
    )
    guide.add_row("  [dim]--verbose / -V[/dim]", "Show all checks, not just failures")
    guide.add_row("  [dim]--spec-only / -s[/dim]", "Only run the 10 spec-required checks")
    guide.add_row("  [dim]--all[/dim]", "Evaluate every skill in the current directory")
    guide.add_row("", "")
    guide.add_row(
        "sklab validate [green]./my-skill[/green]", "Quick pass/fail — exits 0 or 1 (great for CI)"
    )
    guide.add_row("  [dim]--spec-only / -s[/dim]", "Only validate against the Agent Skills spec")
    guide.add_row("  [dim]--all[/dim]", "Validate every skill in the current directory")
    guide.add_row("  [dim]--repo[/dim]", "Validate every skill from the git repo root")
    guide.add_row("", "")
    guide.add_row(
        "sklab scan [green]./my-skill[/green]", "Security scan — shows BLOCK / SUS / ALLOW status"
    )
    guide.add_row("  [dim]--all[/dim]", "Scan every skill in the current directory")
    guide.add_row("", "")
    guide.add_row("sklab list-checks", "Browse all 28 checks across 4 dimensions")
    guide.add_row("  [dim]--spec-only[/dim]", "Only spec-required checks")
    guide.add_row("  [dim]--suggestions-only[/dim]", "Only quality suggestions")
    guide.add_row("", "")
    guide.add_row("sklab stats", "Your personal usage history and score trends")
    guide.add_row("  [dim]count[/dim]", "Skill invocation counts for the current month")
    guide.add_row("  [dim]score[/dim]", "Score trend for all evaluated skills")
    guide.add_row("  [dim]tokens[/dim]", "Token usage per skill for the current month")
    guide.add_row("", "")
    guide.add_row("sklab", "Re-run this guide anytime")

    console.print(
        Panel(
            guide,
            title="[bold]Getting Started[/bold]",
            border_style="dim",
            expand=False,
        )
    )
    console.print()


@app.callback(invoke_without_command=True)
def app_callback(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Evaluate agent skills through static analysis and quality checks."""
    if ctx.invoked_subcommand is None and not _maybe_first_run_scan():
        _print_getting_started()


def _find_repo_root(start: Path) -> Path | None:
    """Walk up from start looking for a .git directory."""
    current = start.resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _discover_skills(root: Path) -> list[Path]:
    """Recursively find all skill directories (containing SKILL.md) under root.

    Skips hidden directories (dot-prefixed) to avoid .git, .claude, etc.
    """
    skills: list[Path] = []
    for path in sorted(root.rglob("SKILL.md")):
        # Skip hidden dirs in the path (e.g. .claude/.skill/...)
        if any(part.startswith(".") for part in path.parts):
            continue
        skills.append(path.parent)
    return skills


def _resolve_skill_path(skill_path: Path | None) -> Path:
    """Resolve and validate a skill directory path.

    Args:
        skill_path: User-provided path, or None for current directory.

    Returns:
        Resolved absolute path.

    Raises:
        typer.Exit: If path doesn't exist, isn't a directory, or has no SKILL.md.
    """
    resolved = Path.cwd() if skill_path is None else skill_path.resolve()
    if not resolved.exists():
        console.print(f"[red]Error: Path does not exist: {resolved}[/red]")
        raise typer.Exit(code=1)
    if not resolved.is_dir():
        console.print(f"[red]Error: Path is not a directory: {resolved}[/red]")
        raise typer.Exit(code=1)
    if not (resolved / "SKILL.md").exists():
        console.print(f"[red]Error: No SKILL.md found in {resolved}[/red]")
        console.print("[dim]This directory does not appear to be a skill folder.[/dim]")
        raise typer.Exit(code=1)
    return resolved


@contextlib.contextmanager
def _cli_error_handler() -> Iterator[None]:
    """Catch exceptions and convert to styled CLI error + exit code 1."""
    try:
        yield
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from None


def _record_telemetry(command: str, start: float, exit_code: int) -> None:
    duration_ms = (time.perf_counter() - start) * 1000
    extras = _pop_telemetry_extras()
    command_event_id: int | None = None
    with contextlib.suppress(Exception):
        command_event_id = record_event(command, duration_ms, exit_code, **extras)
    pending_err = _pop_pending_error()
    if pending_err is not None:
        with contextlib.suppress(Exception):
            record_error(pending_err, command, command_event_id)
    with contextlib.suppress(Exception):
        latest = check_for_update()
        if latest:
            print(
                f"\nsklab {latest} is available (you have {__version__}). "
                f"Run: pip install --upgrade skill-lab",
                file=sys.stderr,
            )


# Params treated as positional args — not captured as flags
_POSITIONAL_PARAMS = {"skill_path", "skill_paths", "trace"}


def _with_telemetry(command_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that wraps a CLI command with init + timing + event recording."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            init_telemetry()
            from skill_lab.core.setup import init_hooks_on_first_run

            init_hooks_on_first_run()

            # Capture boolean flags explicitly set to True
            flags = [
                f"--{k.replace('_', '-')}"
                for k, v in kwargs.items()
                if k not in _POSITIONAL_PARAMS and v is True
            ]
            if flags:
                push_telemetry_extra(flags=flags)

            start = time.perf_counter()
            exit_code = 0
            try:
                return fn(*args, **kwargs)
            except SystemExit as e:
                exit_code = e.code if isinstance(e.code, int) else 0
                raise
            except Exception as e:
                exit_code = 1
                _store_pending_error(e)
                raise
            finally:
                _record_telemetry(command_name, start, exit_code)

        return wrapper

    return decorator


class OutputFormat(str, Enum):
    """Output format options."""

    json = "json"
    console = "console"


# =============================================================================
# Register command modules (must be after app and helpers are defined)
# =============================================================================

import skill_lab.commands  # noqa: E402, F401, I001


# =============================================================================
# Entry point
# =============================================================================


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
