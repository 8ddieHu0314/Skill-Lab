"""Evaluate, validate, and list-checks commands."""

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
from skill_lab.core.models import EvalDimension
from skill_lab.core.registry import registry
from skill_lab.core.telemetry import push_telemetry_extra
from skill_lab.evaluators.static_evaluator import StaticEvaluator
from skill_lab.reporters.console_reporter import SEVERITY_STYLES, ConsoleReporter
from skill_lab.reporters.json_reporter import JsonReporter


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
        with _cli_error_handler():
            report = evaluator.evaluate(sp)

        if format == OutputFormat.json:
            json_reporter = JsonReporter()
            console.print(json_reporter.format(report))
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
) -> None:
    """Evaluate a skill and generate a quality report.

    Run from inside a skill directory, or pass the path as an argument.
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

    with _cli_error_handler():
        evaluator = StaticEvaluator(spec_only=spec_only)
        report = evaluator.evaluate(skill_path)

    # Attach skill name and score to the telemetry event recorded by the decorator
    push_telemetry_extra(
        skill_name=skill_path.name,
        score=report.quality_score,
    )

    if output and format == OutputFormat.console:
        format = OutputFormat.json

    if format == OutputFormat.json:
        json_reporter = JsonReporter()
        if output:
            json_reporter.write_file(report, output)
            console.print(f"Report written to: {output}")
        else:
            console.print(json_reporter.format(report))
    else:
        console_reporter = ConsoleReporter(verbose=verbose)
        console_reporter.report(report)

    if not report.overall_pass:
        raise typer.Exit(code=1)


@app.command()
@_with_telemetry("validate")
def validate(
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
) -> None:
    """Quick validation that reports only high-severity failures."""
    skill_path = _resolve_skill_path(skill_path)

    with _cli_error_handler():
        evaluator = StaticEvaluator(spec_only=spec_only)
        passed, errors = evaluator.validate(skill_path)

    check_count = len(evaluator._get_checks())
    if passed:
        console.print(
            f"[green]Validation passed![/green] ({skill_path.name} \u2014 {check_count} checks)"
        )
    else:
        console.print(f"[red]Validation failed![/red] ({skill_path.name})")
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
            help="Filter by dimension (structure, naming, description, content)",
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
