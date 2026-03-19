"""Generate trigger test cases command."""

import os
from pathlib import Path
from typing import Annotated

import typer

from skill_lab.cli import (
    _cli_error_handler,
    _resolve_skill_path,
    _with_telemetry,
    app,
    console,
)
from skill_lab.core.constants import TESTS_DIR
from skill_lab.core.telemetry import push_telemetry_extra
from skill_lab.triggers.generator import TriggerGenerator


@app.command("generate")
@_with_telemetry("generate")
def generate(
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
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite existing triggers.yaml",
        ),
    ] = False,
) -> None:
    """Generate trigger test cases for a skill using an LLM.

    Reads SKILL.md and generates .skill-lab/tests/triggers.yaml with
    13 test cases across all 4 trigger types (explicit, implicit,
    contextual, negative).

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

    # Check for existing file (prompt unless --force)
    output_path = skill_path / TESTS_DIR / "triggers.yaml"
    if output_path.exists() and not force:
        overwrite = typer.confirm(f"Trigger tests already exist at {output_path}. Overwrite?")
        if not overwrite:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(code=0)
        force = True

    # Resolve model: --model flag > SKLAB_MODEL env var > default
    resolved_model = model or os.environ.get("SKLAB_MODEL") or None

    with _cli_error_handler():
        kwargs: dict[str, str] = {}
        if resolved_model:
            kwargs["model"] = resolved_model

        generator = TriggerGenerator(api_key=api_key, **kwargs)

        with console.status("[cyan]Generating trigger tests...[/cyan]", spinner="dots"):
            written_path = generator.generate_and_write(skill_path, force=force)

    # Print summary
    import yaml

    content = yaml.safe_load(written_path.read_text())
    test_cases = content.get("test_cases", [])
    type_counts: dict[str, int] = {}
    for tc in test_cases:
        t = tc.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    console.print(f"\n[green]Generated {len(test_cases)} trigger tests:[/green]")
    for type_name, count in sorted(type_counts.items()):
        console.print(f"  {type_name}: {count}")

    # Show token usage and cost
    if generator.last_usage:
        usage = generator.last_usage
        cost = usage.total_cost
        cost_str = f" (${cost:.4f})" if cost is not None else ""
        console.print(
            f"\n[dim]Tokens:[/dim] {usage.input_tokens:,} in + "
            f"{usage.output_tokens:,} out = {usage.total_tokens:,}{cost_str}"
        )

    console.print(f"\n[dim]Written to:[/dim] {written_path}")
    console.print("[dim]Run[/dim] sklab trigger [dim]to execute them.[/dim]")
