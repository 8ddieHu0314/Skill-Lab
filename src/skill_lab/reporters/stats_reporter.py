"""Rich terminal reporter for sklab stats commands."""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from skill_lab.core.stats import OverviewStats, SkillCount, SkillScore, SkillTokens

console = Console()


def _score_color(score: float) -> str:
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    return "red"


def print_stats_overview(stats: OverviewStats) -> None:
    lines: list[str] = []

    # Skills fired
    lines.append("[bold]Skills Fired[/bold]")
    lines.append(f"  [dim]{stats.month_label}[/dim]")
    lines.append(f"  [cyan]{stats.skills_fired_this_month}[/cyan] invocations this month")
    lines.append("")
    lines.append(
        "  [dim]\u2192 run [bold]sklab stats count[/bold] to see use count per skill[/dim]"
    )
    lines.append("")

    # Avg score
    lines.append("[bold]Avg Score[/bold]  [dim]All Skills[/dim]")
    if stats.avg_baseline_score is not None and stats.avg_current_score is not None:
        delta = stats.avg_current_score - stats.avg_baseline_score
        sign = "+" if delta >= 0 else ""
        delta_color = "green" if delta >= 0 else "red"
        cur_color = _score_color(stats.avg_current_score)
        lines.append(f"  Baseline   {stats.avg_baseline_score:.1f}")
        lines.append(
            f"  Current    [{cur_color}]{stats.avg_current_score:.1f}[/{cur_color}]"
            f"   [{delta_color}]{sign}{delta:.1f}[/{delta_color}]"
        )
    else:
        lines.append("  [dim]No evaluate runs recorded yet.[/dim]")
        lines.append("  [dim]Run [bold]sklab evaluate ./my-skill[/bold] to start.[/dim]")
    lines.append("")
    lines.append(
        "  [dim]\u2192 run [bold]sklab stats score[/bold] to see score trend per skill[/dim]"
    )
    lines.append("")

    # Tokens
    lines.append("[bold]Tokens from Skills[/bold]")
    lines.append(f"  [dim]{stats.month_label}[/dim]")
    lines.append(
        f"  [cyan]{stats.tokens_this_month:,}[/cyan] tokens"
        "  [dim](estimated from SKILL.md content)[/dim]"
    )
    lines.append("")
    lines.append(
        "  [dim]\u2192 run [bold]sklab stats tokens[/bold] to see tokens used per skill[/dim]"
    )
    lines.append("")

    # Version history
    lines.append("[bold]Version History[/bold]")
    if stats.version_history:
        for version, date in reversed(stats.version_history):
            lines.append(f"  [dim]{date}[/dim]   v{version}")
    else:
        lines.append("  [dim]No version history yet.[/dim]")

    if stats.has_old_data:
        lines.append("")
        lines.append(
            "  [dim]Note: Some evaluate runs were recorded on an older version of sklab"
            " that did not capture skill names or scores.[/dim]"
        )

    console.print(Panel("\n".join(lines), title="[bold]sklab stats[/bold]", expand=False))


def print_stats_count(month_label: str, rows: list[SkillCount]) -> None:
    if not rows:
        console.print(f"[yellow]No skill invocations recorded for {month_label}.[/yellow]")
        console.print(
            "[dim]Run [bold]sklab setup[/bold] to enable automatic invocation tracking.[/dim]"
        )
        return

    total_uses = sum(r.use_count for r in rows)
    total_tokens = sum(r.tokens_used for r in rows)

    table = Table(
        title=f"Skill Use Count  \u2022  {month_label}",
        box=box.ROUNDED,
        show_footer=True,
    )
    table.add_column("Skill Name", style="cyan", footer="Total")
    table.add_column("Use Count", justify="right", footer=str(total_uses))
    table.add_column("Tokens Used", justify="right", footer=f"{total_tokens:,}")

    for row in rows:
        table.add_row(row.skill_name, str(row.use_count), f"{row.tokens_used:,}")

    console.print(table)


def print_stats_score(rows: list[SkillScore]) -> None:
    if not rows:
        console.print("[yellow]No evaluate runs recorded yet.[/yellow]")
        console.print(
            "[dim]Run [bold]sklab evaluate ./my-skill[/bold] to start tracking scores.[/dim]"
        )
        return

    table = Table(title="Skill Score Trend  \u2022  All Time", box=box.ROUNDED)
    table.add_column("Skill Name", style="cyan")
    table.add_column("Current", justify="right")
    table.add_column("Baseline", justify="right")
    table.add_column("\u0394", justify="right")

    for row in rows:
        cur_color = _score_color(row.current_score)
        current_str = f"[{cur_color}]{row.current_score:.1f}[/{cur_color}]"
        baseline_str = f"{row.baseline_score:.1f}"
        if row.is_new:
            delta_str = "[dim]new[/dim]"
        else:
            delta = row.current_score - row.baseline_score
            sign = "+" if delta >= 0 else ""
            delta_color = "green" if delta >= 0 else "red"
            delta_str = f"[{delta_color}]{sign}{delta:.1f}[/{delta_color}]"
        table.add_row(row.skill_name, current_str, baseline_str, delta_str)

    console.print(table)


def print_stats_tokens(month_label: str, rows: list[SkillTokens]) -> None:
    if not rows:
        console.print(f"[yellow]No token data recorded for {month_label}.[/yellow]")
        console.print(
            "[dim]Run [bold]sklab setup[/bold] to enable automatic invocation tracking.[/dim]"
        )
        return

    total_tokens = sum(r.total_tokens for r in rows)

    table = Table(
        title=f"Skill Token Usage  \u2022  {month_label}",
        box=box.ROUNDED,
        show_footer=True,
    )
    table.add_column("Skill Name", style="cyan", footer="Total")
    table.add_column("Tokens / Invocation", justify="right", footer="")
    table.add_column("Total Tokens", justify="right", footer=f"{total_tokens:,}")

    for row in rows:
        table.add_row(
            row.skill_name,
            f"~{row.tokens_per_invocation:,}",
            f"{row.total_tokens:,}",
        )

    console.print(table)
