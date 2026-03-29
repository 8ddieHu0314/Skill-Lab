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
from skill_lab.core.llm import detect_provider_name, get_api_key_env_var
from skill_lab.core.skill_config import resolve_model, update_model
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
            help=(
                "Model ID (default: claude-haiku-4-5-20251001). "
                "Supports Anthropic, OpenAI (gpt-*), and Gemini (gemini-*) models."
            ),
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

    Reads SKILL.md and generates .sklab/tests/triggers.yaml with
    13 test cases across all 4 trigger types (explicit, implicit,
    contextual, negative).

    """
    skill_path = _resolve_skill_path(skill_path)
    push_telemetry_extra(skill_name=skill_path.name)

    # Resolve model: --model flag > config > SKLAB_MODEL env var > default
    resolved_model = resolve_model(model, skill_path)

    # Detect provider and check API key
    provider_name = detect_provider_name(resolved_model)
    env_var = get_api_key_env_var(provider_name)
    api_key = os.environ.get(env_var)
    if not api_key:
        console.print(
            f"[red]Error: {env_var} environment variable is not set.[/red]\n"
            f"[dim]Set it with:[/dim] export {env_var}=your-key-here"
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

    with _cli_error_handler():
        generator = TriggerGenerator(model=resolved_model, api_key=api_key)

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
        cost_str = f" (${usage.total_cost:.4f})" if usage.has_pricing else " (no pricing data)"
        console.print(
            f"\n[dim]Tokens:[/dim] {usage.input_tokens:,} in + "
            f"{usage.output_tokens:,} out = {usage.total_tokens:,}{cost_str}"
        )

    # Persist resolved model to config
    update_model(skill_path, resolved_model)

    console.print(f"\n[dim]Written to:[/dim] {written_path}")
    console.print("[dim]Run[/dim] sklab trigger [dim]to execute them.[/dim]")
