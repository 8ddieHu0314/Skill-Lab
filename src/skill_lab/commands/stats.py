"""Stats subcommands."""

import time
from pathlib import Path
from typing import Annotated

import typer

from skill_lab.cli import _find_repo_root, _record_telemetry, _with_telemetry, app, console
from skill_lab.core.colors import WARN_COLOR
from skill_lab.core.telemetry import _store_pending_error, init_telemetry

stats_app = typer.Typer(
    name="stats",
    help="Show personal usage statistics.",
    invoke_without_command=True,
    add_completion=False,
)
app.add_typer(stats_app)


def _resolve_repo_filter(here: bool) -> Path | None:
    """Return the repo root if --here is set, else None (global)."""
    if not here:
        return None
    root = _find_repo_root(Path.cwd())
    return root if root is not None else Path.cwd()


@stats_app.callback(invoke_without_command=True)
def stats(ctx: typer.Context) -> None:
    """Show usage statistics overview."""
    init_telemetry()
    from skill_lab.core.setup import init_hooks_on_first_run

    init_hooks_on_first_run()

    if ctx.invoked_subcommand is not None:
        return

    start = time.perf_counter()
    exit_code = 0
    try:
        from skill_lab.core.stats import get_overview_stats
        from skill_lab.reporters.stats_reporter import print_stats_overview

        data = get_overview_stats()
        if data is None:
            console.print(f"[{WARN_COLOR}]No usage data found yet.[/{WARN_COLOR}]")
            console.print("[dim]Run some sklab commands first, then check back here.[/dim]")
        else:
            print_stats_overview(data)
    except Exception as e:
        exit_code = 1
        _store_pending_error(e)
        raise
    finally:
        _record_telemetry("stats", start, exit_code)


@stats_app.command("count")
@_with_telemetry("stats-count")
def stats_count(
    here: Annotated[
        bool,
        typer.Option("--here", help="Limit to skills in the current git repo."),
    ] = False,
) -> None:
    """Show skill invocation counts for the current month."""
    from skill_lab.core.stats import get_stats_count
    from skill_lab.reporters.stats_reporter import print_stats_count

    month_label, rows = get_stats_count(repo_root=_resolve_repo_filter(here))
    print_stats_count(month_label, rows)


@stats_app.command("score")
@_with_telemetry("stats-score")
def stats_score(
    here: Annotated[
        bool,
        typer.Option("--here", help="Limit to skills in the current git repo."),
    ] = False,
) -> None:
    """Show score trend for all evaluated skills."""
    from skill_lab.core.stats import get_stats_score
    from skill_lab.reporters.stats_reporter import print_stats_score

    rows = get_stats_score(repo_root=_resolve_repo_filter(here))
    print_stats_score(rows)


@stats_app.command("tokens")
@_with_telemetry("stats-tokens")
def stats_tokens(
    here: Annotated[
        bool,
        typer.Option("--here", help="Limit to skills in the current git repo."),
    ] = False,
) -> None:
    """Show token usage per skill for the current month."""
    from skill_lab.core.stats import get_stats_tokens
    from skill_lab.reporters.stats_reporter import print_stats_tokens

    month_label, rows = get_stats_tokens(repo_root=_resolve_repo_filter(here))
    print_stats_tokens(month_label, rows)
