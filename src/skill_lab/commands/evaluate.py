"""Evaluate, check, and list-checks commands."""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from skill_lab.cli import (
    OutputFormat,
    _cli_error_handler,
    _discover_skills,
    _find_repo_root,
    _resolve_skill_path,
    _with_telemetry,
    app,
    console,
)
from skill_lab.core.eval_history import save_eval
from skill_lab.core.exceptions import GenerationError
from skill_lab.core.llm import GenerationUsage, detect_provider_name, get_api_key_env_var
from skill_lab.core.models import EvalDimension, EvaluationReport, JudgeResult
from skill_lab.core.registry import registry
from skill_lab.core.skill_config import resolve_model, update_evaluate, update_model, update_review
from skill_lab.core.telemetry import push_telemetry_extra
from skill_lab.evaluators.static_evaluator import StaticEvaluator
from skill_lab.reporters.console_reporter import SEVERITY_STYLES, ConsoleReporter
from skill_lab.reporters.json_reporter import JsonReporter

logger = logging.getLogger(__name__)

OPTIMIZE_SCORE_THRESHOLD = 75


def _run_bulk_evaluate(
    roots: list[Path],
    verbose: bool,
    spec_only: bool,
    format: "OutputFormat",
) -> None:
    """Discover and evaluate all skills under the given root directories."""
    skill_paths: list[Path] = []
    for root in roots:
        found = _discover_skills(root)
        skill_paths.extend(found)

    if not skill_paths:
        console.print("[yellow]No skill folders found (no SKILL.md files discovered).[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"[dim]Found {len(skill_paths)} skill(s). Running evaluate...[/dim]\n")

    evaluator = StaticEvaluator(spec_only=spec_only)
    any_failed = False
    summary_rows: list[tuple[str, str, str, str]] = []  # name, path, score, status

    for sp in skill_paths:
        try:
            report = evaluator.evaluate(sp)
        except Exception as e:
            console.print(f"[red]Error evaluating {sp.name}: {e}[/red]")
            any_failed = True
            continue

        if format == OutputFormat.json:
            json_reporter = JsonReporter()
            console.print(json_reporter.format(report), soft_wrap=True)
        else:
            console_reporter = ConsoleReporter(verbose=verbose)
            console_reporter.report(report)

        score_str = f"{report.quality_score:.1f}"
        status_str = "[green]PASS[/green]" if report.overall_pass else "[red]FAIL[/red]"
        skill_name = report.skill_name or sp.name
        rel_path = str(sp.relative_to(Path.cwd())) if sp.is_relative_to(Path.cwd()) else str(sp)
        summary_rows.append((skill_name, rel_path, score_str, status_str))

        if not report.overall_pass:
            any_failed = True

    if summary_rows:
        scores = [float(row[2]) for row in summary_rows]
        push_telemetry_extra(
            skill_name=f"bulk({len(summary_rows)})",
            score=round(sum(scores) / len(scores), 2),
        )

    # Summary table
    if format == OutputFormat.console:
        console.print()
        table = Table(title=f"Summary \u2014 {len(skill_paths)} skill(s)", box=box.ROUNDED)
        table.add_column("Skill", style="cyan")
        table.add_column("Path", style="dim")
        table.add_column("Score", justify="right")
        table.add_column("Status", justify="center")
        for name, path, score, status in summary_rows:
            table.add_row(name, path, score, status)
        console.print(table)

    if any_failed:
        raise typer.Exit(code=1)


@app.command()
@_with_telemetry("evaluate")
def evaluate(
    skill_path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the skill directory (defaults to current directory)",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file path (for JSON output)",
        ),
    ] = None,
    format: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format",
        ),
    ] = OutputFormat.console,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-V",
            help="Show all checks, not just failures",
        ),
    ] = False,
    spec_only: Annotated[
        bool,
        typer.Option(
            "--spec-only",
            "-s",
            help="Only run checks required by the Agent Skills spec (skip quality suggestions)",
        ),
    ] = False,
    all_skills: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Discover and evaluate all skills in the current directory (recursive)",
        ),
    ] = False,
    repo: Annotated[
        bool,
        typer.Option(
            "--repo",
            help="Discover and evaluate all skills from the git repo root (recursive)",
        ),
    ] = False,
    skip_review: Annotated[
        bool,
        typer.Option(
            "--skip-review",
            help="Skip LLM quality review (static checks only)",
        ),
    ] = False,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help=(
                "Model for LLM quality review (default: claude-haiku-4-5-20251001). "
                "Supports Anthropic, OpenAI (gpt-*), and Gemini (gemini-*) models."
            ),
        ),
    ] = None,
    optimize: Annotated[
        bool,
        typer.Option(
            "--optimize",
            help="Automatically run optimization after evaluation (skips the interactive prompt)",
        ),
    ] = False,
) -> None:
    """Evaluate a skill: static checks + LLM quality review.

    Run from inside a skill directory, or pass the path as an argument.
    Runs 37 static checks, then sends the skill to an LLM judge that
    scores it on 8 criteria across Activation and Instruction axes.

    LLM review requires an API key (ANTHROPIC_API_KEY, OPENAI_API_KEY,
    or GEMINI_API_KEY). Use --skip-review for static-only evaluation.
    """
    # --all and --repo are mutually exclusive with a positional path
    if (all_skills or repo) and skill_path is not None:
        console.print("[red]Error: Cannot combine --all/--repo with a skill path argument.[/red]")
        raise typer.Exit(code=1)

    if all_skills and repo:
        console.print("[red]Error: --all and --repo are mutually exclusive.[/red]")
        raise typer.Exit(code=1)

    if all_skills:
        _run_bulk_evaluate([Path.cwd()], verbose, spec_only, format)
        return

    if repo:
        repo_root = _find_repo_root(Path.cwd())
        if repo_root is None:
            console.print("[red]Error: Not inside a git repository.[/red]")
            raise typer.Exit(code=1)
        console.print(f"[dim]Repo root: {repo_root}[/dim]")
        _run_bulk_evaluate([repo_root], verbose, spec_only, format)
        return

    skill_path = _resolve_skill_path(skill_path)

    # Phase 1: Static evaluation (always runs)
    with _cli_error_handler():
        evaluator = StaticEvaluator(spec_only=spec_only)
        report = evaluator.evaluate(skill_path)

    update_evaluate(
        skill_path,
        score=report.quality_score,
        checks_passed=report.checks_passed,
        checks_total=report.checks_run,
        date=report.timestamp,
    )

    push_telemetry_extra(
        skill_name=skill_path.name,
        score=report.quality_score,
    )

    if output and format == OutputFormat.console:
        format = OutputFormat.json

    # Phase 2: LLM judge (if API key available and not skipped)
    judge_result: JudgeResult | None = None
    judge_usage = None
    missing_env_var: str | None = None
    resolved_model: str | None = None

    if not skip_review:
        judge_result, judge_usage, missing_env_var, resolved_model = _try_llm_review(
            skill_path, model
        )

    # Persist full evaluation to history (.sklab/evals/)
    _save_eval_history(skill_path, report, judge_result, resolved_model, judge_usage)

    # Render output
    if format == OutputFormat.json:
        json_reporter = JsonReporter()
        if output:
            json_reporter.write_file(
                report, output, judge_result=judge_result, judge_usage=judge_usage
            )
            console.print(f"Report written to: {output}")
        else:
            console.print(
                json_reporter.format(report, judge_result=judge_result, judge_usage=judge_usage),
                soft_wrap=True,
            )
    else:
        console_reporter = ConsoleReporter(verbose=verbose)
        console_reporter.report(report)
        if judge_result is not None:
            console_reporter.report_judge(judge_result, usage=judge_usage)
        elif missing_env_var:
            _print_api_key_hint(missing_env_var)

    # Chain into optimization: --optimize flag (unconditional) or interactive prompt (score < 75)
    if optimize and not all_skills and not repo:
        _run_optimize(skill_path, model)
    elif (
        format == OutputFormat.console
        and not all_skills
        and not repo
        and report.quality_score < OPTIMIZE_SCORE_THRESHOLD
    ):
        _offer_optimize(skill_path, model)

    if not report.overall_pass:
        raise typer.Exit(code=1)


def _try_llm_review(
    skill_path: Path,
    model: str | None,
) -> tuple[JudgeResult | None, GenerationUsage | None, str | None, str | None]:
    """Attempt LLM judge review.

    Returns:
        (result, usage, missing_env_var, resolved_model) — missing_env_var is
        set when the API key is absent so the caller can print a hint without
        re-resolving the model.
    """
    from skill_lab.judge.judge import SkillJudge

    resolved_model = resolve_model(model, skill_path)
    provider_name = detect_provider_name(resolved_model)
    env_var = get_api_key_env_var(provider_name)
    api_key = os.environ.get(env_var)

    if not api_key:
        return None, None, env_var, resolved_model

    try:
        judge = SkillJudge(model=resolved_model, api_key=api_key)
        with console.status("[cyan]Running LLM quality review...[/cyan]", spinner="dots"):
            result = judge.review(skill_path)

        update_review(
            skill_path,
            judge_score=result.judge_score,
            activation_score=result.activation_score,
            instruction_score=result.instruction_score,
            date=datetime.now(timezone.utc).isoformat(),
        )
        update_model(skill_path, resolved_model)

        push_telemetry_extra(judge_score=result.judge_score)

        return result, judge.last_usage, None, resolved_model
    except GenerationError as e:
        console.print(f"\n[yellow]LLM review failed:[/yellow] {e.message}")
        if e.suggestion:
            console.print(f"[dim]{e.suggestion}[/dim]")
        return None, None, None, resolved_model


def _print_api_key_hint(env_var: str) -> None:
    """Print a hint about setting an API key for LLM review."""
    console.print(
        f"\n[yellow]LLM quality review skipped[/yellow] — {env_var} not set.\n"
        f"  [dim]Set [bold]{env_var}[/bold] to enable 8-criterion LLM analysis,\n"
        f"  or use [bold]--skip-review[/bold] to suppress this message.[/dim]\n"
    )


def _save_eval_history(
    skill_path: Path,
    report: EvaluationReport,
    judge_result: JudgeResult | None,
    resolved_model: str | None,
    judge_usage: GenerationUsage | None,
) -> None:
    """Persist full evaluation to .sklab/evals/ (best-effort, never fails the command)."""
    try:
        save_eval(
            skill_path,
            report,
            judge_result=judge_result,
            judge_model=resolved_model if judge_result else None,
            judge_usage=judge_usage.to_dict() if judge_usage else None,
        )
    except Exception:
        logger.debug("Failed to save eval history", exc_info=True)


def _run_optimize(skill_path: Path, model: str | None) -> None:
    """Chain into optimization unconditionally (--optimize flag)."""
    from skill_lab.commands.optimize import _run_optimize_from_eval

    _run_optimize_from_eval(skill_path, model)


def _offer_optimize(skill_path: Path, model: str | None) -> None:
    """Prompt user to run optimize if score is below threshold."""
    if not sys.stdin.isatty():
        return
    console.print()
    if typer.confirm("Score below 75. Optimize?", default=False):
        _run_optimize(skill_path, model)


def _run_bulk_check(roots: list[Path], spec_only: bool) -> None:
    """Discover and check all skills under the given root directories."""
    skill_paths: list[Path] = []
    for root in roots:
        skill_paths.extend(_discover_skills(root))

    if not skill_paths:
        console.print("[yellow]No skill folders found (no SKILL.md files discovered).[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"[dim]Found {len(skill_paths)} skill(s). Running check...[/dim]\n")

    evaluator = StaticEvaluator(spec_only=spec_only, include_security=True)
    any_failed = False
    summary_rows: list[tuple[str, str, str]] = []

    for sp in skill_paths:
        try:
            passed, errors = evaluator.check(sp)
        except Exception as e:
            console.print(f"[red]Error checking {sp.name}: {e}[/red]")
            any_failed = True
            continue

        skill_name = sp.name
        rel_path = str(sp.relative_to(Path.cwd())) if sp.is_relative_to(Path.cwd()) else str(sp)

        if passed:
            summary_rows.append((skill_name, rel_path, "[green]PASS[/green]"))
        else:
            console.print(f"[bold]{skill_name}[/bold] ({rel_path})")
            for error in errors:
                console.print(f"  [red]X[/red] [{error.check_id}] {error.message}")
            console.print(
                f"  [dim]Run [bold]sklab evaluate {rel_path}[/bold] for full details.[/dim]"
            )
            console.print()
            any_failed = True
            summary_rows.append((skill_name, rel_path, "[red]FAIL[/red]"))

    console.print()
    table = Table(title=f"Summary — {len(skill_paths)} skill(s)", box=box.ROUNDED)
    table.add_column("Skill", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Status", justify="center")
    for name, path, status in summary_rows:
        table.add_row(name, path, status)
    console.print(table)

    if any_failed:
        raise typer.Exit(code=1)


@app.command()
@_with_telemetry("check")
def check(
    skill_path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the skill directory (defaults to current directory)",
        ),
    ] = None,
    spec_only: Annotated[
        bool,
        typer.Option(
            "--spec-only",
            "-s",
            help="Only run checks required by the Agent Skills spec (skip quality suggestions)",
        ),
    ] = False,
    all_skills: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Discover and check all skills in the current directory (recursive)",
        ),
    ] = False,
    repo: Annotated[
        bool,
        typer.Option(
            "--repo",
            help="Discover and check all skills from the git repo root (recursive)",
        ),
    ] = False,
) -> None:
    """Quick validation that reports only high-severity failures."""
    if (all_skills or repo) and skill_path is not None:
        console.print("[red]Error: Cannot combine --all/--repo with a skill path argument.[/red]")
        raise typer.Exit(code=1)

    if all_skills and repo:
        console.print("[red]Error: --all and --repo are mutually exclusive.[/red]")
        raise typer.Exit(code=1)

    if all_skills:
        _run_bulk_check([Path.cwd()], spec_only)
        return

    if repo:
        repo_root = _find_repo_root(Path.cwd())
        if repo_root is None:
            console.print("[red]Error: Not inside a git repository.[/red]")
            raise typer.Exit(code=1)
        console.print(f"[dim]Repo root: {repo_root}[/dim]")
        _run_bulk_check([repo_root], spec_only)
        return

    skill_path = _resolve_skill_path(skill_path)

    with _cli_error_handler():
        evaluator = StaticEvaluator(spec_only=spec_only, include_security=True)
        passed, errors = evaluator.check(skill_path)

    push_telemetry_extra(skill_name=skill_path.name)

    check_count = len(evaluator._get_checks())
    if passed:
        console.print(
            f"[green]Check passed![/green] ({skill_path.name} \u2014 {check_count} checks)"
        )
    else:
        console.print(f"[red]Check failed![/red] ({skill_path.name})")
        console.print()
        for error in errors:
            console.print(f"  [red]X[/red] [{error.check_id}] {error.message}")
        console.print()
        raise typer.Exit(code=1)


@app.command("list-checks")
@_with_telemetry("list-checks")
def list_checks(
    dimension: Annotated[
        str | None,
        typer.Option(
            "--dimension",
            "-d",
            help="Filter by dimension (structure, naming, description, content, security)",
        ),
    ] = None,
    spec_only: Annotated[
        bool,
        typer.Option(
            "--spec-only",
            "-s",
            help="Only show checks required by the Agent Skills spec",
        ),
    ] = False,
    suggestions_only: Annotated[
        bool,
        typer.Option(
            "--suggestions-only",
            help="Only show quality suggestion checks (not spec-required)",
        ),
    ] = False,
) -> None:
    """List all available checks."""
    # Get checks
    if dimension:
        try:
            dim = EvalDimension(dimension.lower())
            checks = registry.get_by_dimension(dim.value)
        except ValueError:
            console.print(f"[red]Invalid dimension: {dimension}[/red]")
            console.print(f"Valid dimensions: {', '.join(d.value for d in EvalDimension)}")
            raise typer.Exit(code=1) from None
    elif spec_only:
        checks = registry.get_spec_required()
    elif suggestions_only:
        checks = registry.get_quality_suggestions()
    else:
        checks = registry.get_all()
    checks = [c for c in checks if c.listable]

    if not checks:
        console.print("[yellow]No checks found.[/yellow]")
        return

    # Build table
    table = Table(title="Available Checks")
    table.add_column("Check ID", style="cyan")
    table.add_column("Name")
    table.add_column("Dimension", style="blue")
    table.add_column("Severity")
    table.add_column("Spec", style="green")
    table.add_column("Description")

    for check_class in sorted(checks, key=lambda c: c.check_id):
        severity_style = SEVERITY_STYLES.get(check_class.severity.value, "white")
        spec_badge = "[green]Yes[/green]" if check_class.spec_required else "[dim]No[/dim]"
        table.add_row(
            check_class.check_id,
            check_class.check_name,
            check_class.dimension.value,
            f"[{severity_style}]{check_class.severity.value}[/{severity_style}]",
            spec_badge,
            check_class.description,
        )

    console.print(table)
    spec_count = sum(1 for c in checks if c.spec_required)
    console.print(
        f"\nTotal: {len(checks)} checks ({spec_count} spec-required,"
        f" {len(checks) - spec_count} quality suggestions)"
    )
