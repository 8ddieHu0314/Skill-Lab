"""Optimize a SKILL.md using LLM-powered analysis."""

import difflib
import os
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.text import Text

from skill_lab.cli import (
    _cli_error_handler,
    _resolve_skill_path,
    _with_telemetry,
    app,
    console,
)
from skill_lab.core.eval_history import EvalRecord, load_latest_eval
from skill_lab.core.llm import detect_provider_name, get_api_key_env_var
from skill_lab.core.skill_config import load_config, resolve_model, save_config, update_model
from skill_lab.core.telemetry import push_telemetry_extra
from skill_lab.optimizer.optimizer import OptimizationResult, SkillOptimizer

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@.*$")


def _build_diff_text(raw_diff: str) -> Text:
    """Build a Rich Text from a unified diff with human-readable formatting.

    - Strips redundant file headers (--- / +++)
    - Skips @@ hunk markers (line numbers shown inline instead)
    - Prepends the file line number to each removed/added line
    - Colors removed lines red, added lines green
    - Each line is appended separately so word-wrap never bleeds between lines
    """
    text = Text()
    old_line = 0
    new_line = 0
    first_hunk = True
    for line in raw_diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_line = int(m.group(1))
            new_line = int(m.group(2))
            if not first_hunk:
                text.append("\n")
            first_hunk = False
        elif line.startswith("-"):
            text.append(f"{old_line:4d} ", style="dim red")
            text.append(line + "\n", style="red")
            old_line += 1
        elif line.startswith("+"):
            text.append(f"{new_line:4d} ", style="dim green")
            text.append(line + "\n", style="green")
            new_line += 1
        else:
            text.append(f"     {line}\n")
            old_line += 1
            new_line += 1
    return text


def _increment_patch(version: str) -> str:
    """Increment the patch component of a semver string.

    Falls back to appending '.1' if the last component is non-numeric
    (e.g. pre-release suffixes like "1.0.0-beta").

    Examples:
        "0.2.0" -> "0.2.1"
        "1.0" -> "1.1"
        "1.0.0-beta" -> "1.0.0-beta.1"
    """
    parts = version.split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
    except ValueError:
        parts.append("1")
    return ".".join(parts)


def _prompt_version_bump(skill_path: Path, *, auto: bool = False) -> None:
    """Ask user if they want to bump the skill version after optimization.

    Skips the prompt entirely in --auto mode or non-TTY environments.
    """
    if auto or not sys.stdin.isatty():
        return
    config = load_config(skill_path)
    current = config.version or "0.0.0"
    console.print(f"\n[dim]Current version: {current}[/dim]")
    if typer.confirm("Bump skill version?", default=False):
        default_next = _increment_patch(current)
        new_version = typer.prompt("New version", default=default_next)
        updated = replace(config, version=new_version)
        save_config(skill_path, updated)
        console.print(f"[green]Version updated to {new_version}[/green]")


def _show_result_and_apply(
    skill_path: Path,
    result: OptimizationResult,
    resolved_model: str,
    eval_record: EvalRecord,
    auto: bool,
) -> None:
    """Display optimization result, apply if confirmed, and prompt version bump."""
    # Check if content changed
    if result.original_content == result.optimized_content:
        console.print(f"\n[green]Already optimized![/green] Score: {result.original_score}/100")
        return

    # Show evaluation summary
    score_line = f"\n[dim]Current score:[/dim] {result.original_score}/100"
    if eval_record.judge is not None:
        score_line += f" | [dim]Judge:[/dim] {eval_record.judge.judge_score}/100"
    score_line += f" ({result.original_failures} issues)"
    console.print(score_line)

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
                _build_diff_text(diff_text),
                title="Proposed Changes",
                subtitle="[dim]- removed  + added[/dim]",
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
        cost_str = f" (${usage.total_cost:.4f})" if usage.has_pricing else " (no pricing data)"
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

        # Persist resolved model and prompt version bump
        update_model(skill_path, resolved_model)
        _prompt_version_bump(skill_path, auto=auto)
    else:
        console.print("[dim]Changes discarded.[/dim]")
        push_telemetry_extra(applied=False)


def _run_optimize_from_eval(
    skill_path: Path,
    model: str | None,
    auto: bool = False,
) -> None:
    """Run optimization using latest eval history.

    Shared entry point called by both the optimize command and the evaluate chain.

    Args:
        skill_path: Resolved path to the skill directory.
        model: Raw --model flag value (None = use resolution chain).
        auto: If True, skip confirmation prompts.
    """
    eval_record = load_latest_eval(skill_path)
    if eval_record is None:
        console.print(
            "[red]Error: No evaluation results found.[/red]\n"
            "[dim]Run [bold]sklab evaluate[/bold] first to generate evaluation history.[/dim]"
        )
        raise typer.Exit(code=1)

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

    # Show what eval we're using (strip timezone suffix for readability)
    eval_date = eval_record.report.timestamp.replace("T", " ")[:19]
    eval_info = f"[dim]Using evaluation from {eval_date} (static: {eval_record.report.quality_score:.0f}/100"
    if eval_record.judge is not None:
        eval_info += f", judge: {eval_record.judge.judge_score:.0f}/100"
    eval_info += ")[/dim]"
    console.print(eval_info)

    with _cli_error_handler():
        optimizer = SkillOptimizer(model=resolved_model, api_key=api_key)

        with console.status("[cyan]Optimizing...[/cyan]", spinner="dots"):
            result = optimizer.optimize_from_history(skill_path, eval_record)

    _show_result_and_apply(skill_path, result, resolved_model, eval_record, auto)


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
            help=(
                "Model ID (default: claude-haiku-4-5-20251001). "
                "Supports Anthropic, OpenAI (gpt-*), and Gemini (gemini-*) models."
            ),
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

    Reads the latest evaluation from .sklab/evals/ (run `sklab evaluate` first),
    sends static failures and LLM judge feedback to an LLM, and proposes
    improvements. Shows a diff and score delta before applying.

    Requires an API key for the selected provider (ANTHROPIC_API_KEY,
    OPENAI_API_KEY, or GEMINI_API_KEY).
    """
    skill_path = _resolve_skill_path(skill_path)
    push_telemetry_extra(skill_name=skill_path.name)
    _run_optimize_from_eval(skill_path, model, auto=auto)
