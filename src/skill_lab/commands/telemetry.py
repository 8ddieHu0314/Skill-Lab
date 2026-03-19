"""Telemetry subcommands."""

from typing import Annotated

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from skill_lab.cli import app, console

telemetry_app = typer.Typer(
    name="telemetry",
    help="Manage telemetry settings and data.",
    invoke_without_command=True,
    add_completion=False,
)
app.add_typer(telemetry_app)


def _telemetry_status() -> None:
    """Render telemetry status panel."""
    from skill_lab.core.telemetry import get_telemetry_status

    status = get_telemetry_status()
    state = "[green]enabled[/green]" if status["enabled"] else "[red]disabled[/red]"
    lines = [f"  Status: {state}"]
    if status["env_override"]:
        lines.append(f"  Env override: [yellow]{status['env_override']}[/yellow]")
    lines.append(f"  Database: {status['db_path']}")
    if status["db_exists"]:
        size_kb = status["db_size_bytes"] / 1024
        lines.append(f"  Database size: {size_kb:.1f} KB")
        for table, count in status["row_counts"].items():
            lines.append(f"  {table}: {count} rows")
    else:
        lines.append("  [dim]No database file yet.[/dim]")
    console.print(Panel("\n".join(lines), title="Telemetry Status", expand=False))


@telemetry_app.callback(invoke_without_command=True)
def telemetry_callback(ctx: typer.Context) -> None:
    """Show telemetry status (default when no subcommand given)."""
    if ctx.invoked_subcommand is None:
        _telemetry_status()


@telemetry_app.command("enable")
def telemetry_enable() -> None:
    """Enable anonymous usage telemetry."""
    from skill_lab.core.telemetry import enable_telemetry

    enable_telemetry()
    console.print("[green]Telemetry enabled.[/green]")


@telemetry_app.command("disable")
def telemetry_disable() -> None:
    """Disable anonymous usage telemetry."""
    from skill_lab.core.telemetry import disable_telemetry

    console.print(
        "[yellow]Warning:[/yellow] Disabling telemetry stops all local data collection. "
        "You will no longer accumulate data for [bold]sklab stats[/bold] "
        "(invocation counts, score trends, token usage)."
    )
    confirmed = typer.confirm("Disable telemetry?", default=True)
    if not confirmed:
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(code=0)

    disable_telemetry()
    console.print("[yellow]Telemetry disabled.[/yellow]")


@telemetry_app.command("show")
def telemetry_show(
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Number of events to show."),
    ] = 20,
    json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON array."),
    ] = False,
) -> None:
    """Show recent telemetry events."""
    from skill_lab.core.telemetry import get_recent_events

    events = get_recent_events(limit=limit)
    if not events:
        console.print("[dim]No events recorded yet.[/dim]")
        return

    if json:
        import json as json_mod

        data = [
            {
                "timestamp": e.timestamp,
                "command": e.command,
                "duration_ms": e.duration_ms,
                "skill_name": e.skill_name,
                "score": e.score,
                "synced": e.synced,
            }
            for e in events
        ]
        print(json_mod.dumps(data, indent=2))  # noqa: T201
        return

    table = Table(title=f"Recent Events (last {len(events)})", box=box.ROUNDED)
    table.add_column("Timestamp", style="dim")
    table.add_column("Command", style="cyan")
    table.add_column("Duration", justify="right")
    table.add_column("Skill")
    table.add_column("Score", justify="right")
    table.add_column("Synced", justify="center")

    for e in events:
        ts = e.timestamp[:19] if e.timestamp else ""
        dur = f"{e.duration_ms:.0f}ms" if e.duration_ms is not None else ""
        score = f"{e.score:.1f}" if e.score is not None else ""
        synced = "[green]Y[/green]" if e.synced else "[dim]N[/dim]"
        table.add_row(ts, e.command, dur, e.skill_name or "", score, synced)

    console.print(table)
