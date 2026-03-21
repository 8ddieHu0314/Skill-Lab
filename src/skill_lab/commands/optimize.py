"""Optimize a SKILL.md using LLM-powered analysis."""

import difflib
import os
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.syntax import Syntax

from skill_lab.cli import (
    _cli_error_handler,
    _resolve_skill_path,
    _with_telemetry,
    app,
    console,
)
from skill_lab.core.telemetry import push_telemetry_extra
from skill_lab.optimizer.optimizer import SkillOptimizer


@app.command("optimize")
@_with_telemetry("optimize")
def optimize(
    skill_path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the skill directory (defaults to current directory)",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help="Anthropic model ID (default: claude-haiku-4-5-20251001)",
        ),
    ] = None,
    auto: Annotated[
        bool,
        typer.Option(
            "--auto",
            help="Apply changes without confirmation prompt",
        ),
    ] = False,
) -> None:
    """Optimize a SKILL.md using LLM-powered analysis.

    Evaluates the skill, sends failures to an LLM, and proposes
    improvements. Shows a diff and score delta before applying.

    Requires ANTHROPIC_API_KEY environment variable.
    """
    skill_path = _resolve_skill_path(skill_path)
    push_telemetry_extra(skill_name=skill_path.name)

    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[red]Error: ANTHROPIC_API_KEY environment variable is not set.[/red]\n"
            "[dim]Set it with:[/dim] export ANTHROPIC_API_KEY=sk-..."
        )
        raise typer.Exit(code=1)

    # Resolve model: --model flag > SKLAB_MODEL env var > default
    resolved_model = model or os.environ.get("SKLAB_MODEL") or None

    with _cli_error_handler():
        kwargs: dict[str, str] = {}
        if resolved_model:
            kwargs["model"] = resolved_model

        optimizer = SkillOptimizer(api_key=api_key, **kwargs)

        with console.status("[cyan]Evaluating and optimizing...[/cyan]", spinner="dots"):
            result = optimizer.optimize(skill_path)

    # Check if content changed
    if result.original_content == result.optimized_content:
        console.print(f"\n[green]Already optimized![/green] Score: {result.original_score}/100")
        raise typer.Exit(code=0)

    # Show evaluation summary
    console.print(
        f"\n[dim]Current score:[/dim] {result.original_score}/100 "
        f"({result.original_failures} issues)"
    )

    # Show diff
    diff_lines = list(
        difflib.unified_diff(
            result.original_content.splitlines(keepends=True),
            result.optimized_content.splitlines(keepends=True),
            fromfile="SKILL.md (original)",
            tofile="SKILL.md (optimized)",
        )
    )
    diff_text = "".join(diff_lines)

    if diff_text:
        console.print()
        console.print(
            Panel(
                Syntax(diff_text, "diff", theme="monokai", word_wrap=True),
                title="Proposed Changes",
                border_style="cyan",
            )
        )

    # Show score delta
    delta = result.optimized_score - result.original_score
    if delta > 0:
        delta_str = f"[green]+{delta:.0f}[/green]"
    elif delta < 0:
        delta_str = f"[red]{delta:.0f}[/red]"
    else:
        delta_str = "[dim]+0[/dim]"

    console.print(
        f"\n[bold]Score:[/bold] {result.original_score:.0f} → "
        f"{result.optimized_score:.0f} ({delta_str})"
    )

    # Show token usage and cost
    if result.usage:
        usage = result.usage
        cost_str = f" (${usage.total_cost:.4f})"
        console.print(
            f"[dim]Tokens:[/dim] {usage.input_tokens:,} in + "
            f"{usage.output_tokens:,} out = {usage.total_tokens:,}{cost_str}"
        )

    # Confirm and apply
    push_telemetry_extra(
        score_before=result.original_score,
        score_after=result.optimized_score,
    )

    if auto:
        apply = True
    else:
        console.print()
        apply = typer.confirm("Apply changes?")

    if apply:
        skill_md = skill_path / "SKILL.md"
        skill_md.write_text(result.optimized_content, encoding="utf-8")
        console.print(f"\n[green]Changes applied to {skill_md}[/green]")
        push_telemetry_extra(applied=True)
    else:
        console.print("[dim]Changes discarded.[/dim]")
        push_telemetry_extra(applied=False)
