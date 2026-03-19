"""Trigger test command."""

import json as json_module
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from skill_lab.cli import (
    OutputFormat,
    _resolve_skill_path,
    _with_telemetry,
    app,
    console,
)
from skill_lab.core.constants import TESTS_DIR
from skill_lab.core.models import TriggerReport, TriggerType
from skill_lab.core.telemetry import push_telemetry_extra
from skill_lab.triggers.trigger_evaluator import TriggerEvaluator


def _format_duration(ms: float) -> str:
    """Format duration in human-readable form."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.1f}s"


def _print_trigger_report(report: TriggerReport) -> None:
    """Print a trigger test report to console."""
    console.print()

    # Compact header line
    duration = _format_duration(report.duration_ms)
    pass_status = (
        f"[green]{report.tests_passed}/{report.tests_run} passed[/green]"
        if report.overall_pass
        else f"[red]{report.tests_passed}/{report.tests_run} passed[/red]"
    )
    console.print(
        f"[bold]Trigger Test Report:[/bold] {report.skill_name}\n"
        f"[dim]Runtime:[/dim] {report.runtime} [dim]\u2502[/dim] "
        f"[dim]Duration:[/dim] {duration} [dim]\u2502[/dim] "
        f"{pass_status}"
    )
    console.print()

    # Results table with borders
    table = Table(box=box.ROUNDED, padding=(0, 1))
    table.add_column("Test", style="cyan", no_wrap=True)
    table.add_column("Type", style="dim")
    table.add_column("Status", justify="center")  # Status column

    for result in report.results:
        status = "[green]\u2713[/green]" if result.passed else "[red]\u2717[/red]"
        table.add_row(
            result.test_name,
            result.trigger_type.value,
            status,
        )

    console.print(table)
    console.print()

    # Summary by type - compact inline format
    if report.summary_by_type:
        parts = []
        for type_name, stats in report.summary_by_type.items():
            passed = stats["passed"]
            total = stats["total"]
            pct = (passed / total * 100) if total > 0 else 0
            color = "green" if passed == total else "yellow" if passed > 0 else "red"
            parts.append(f"{type_name}: [{color}]{passed}/{total}[/{color}] ({pct:.0f}%)")
        console.print("[dim]By type:[/dim] " + " [dim]\u2502[/dim] ".join(parts))
        console.print()


@app.command("trigger")
@_with_telemetry("trigger")
def trigger(
    skill_path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the skill directory (defaults to current directory)",
        ),
    ] = None,
    runtime: Annotated[
        str,
        typer.Option(
            "--runtime",
            "-r",
            help="Runtime to use (claude only, codex coming in v0.3.0)",
            hidden=True,
        ),
    ] = "claude",
    type_filter: Annotated[
        str | None,
        typer.Option(
            "--type",
            "-t",
            help="Only run tests of this trigger type (explicit, implicit, contextual, negative)",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file path for JSON report",
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
) -> None:
    """Run trigger tests to verify skill activation.

    Tests whether the skill activates correctly for different prompt types:
    - explicit: Skill named directly with $ prefix
    - implicit: Describes exact scenario without naming skill
    - contextual: Realistic noisy prompt with domain context
    - negative: Should NOT trigger (catches false positives)

    Requires test definitions in .sklab/tests/scenarios.yaml or .sklab/tests/triggers.yaml.
    """
    skill_path = _resolve_skill_path(skill_path)
    push_telemetry_extra(skill_name=skill_path.name)

    # Check for trigger test files
    tests_dir = skill_path / TESTS_DIR
    has_tests = (
        tests_dir.exists() and any(f.suffix in (".yaml", ".yml") for f in tests_dir.iterdir())
        if tests_dir.exists()
        else False
    )
    if not has_tests:
        console.print("[yellow]No trigger tests found.[/yellow]")
        console.print(
            f"[dim]Run [bold]sklab generate {skill_path}[/bold] to auto-generate "
            f"trigger tests, or create them manually at "
            f".sklab/tests/triggers.yaml[/dim]"
        )
        raise typer.Exit(code=1)

    # Parse type filter
    trigger_type: TriggerType | None = None
    if type_filter:
        try:
            trigger_type = TriggerType(type_filter.lower())
        except ValueError:
            console.print(f"[red]Invalid trigger type: {type_filter}[/red]")
            console.print(f"Valid types: {', '.join(t.value for t in TriggerType)}")
            raise typer.Exit(code=1) from None

    # Run evaluation with progress display
    evaluator = TriggerEvaluator(runtime=runtime)

    with console.status("", spinner="dots") as status:

        def update_progress(current: int, total: int, test_name: str) -> None:
            status.update(f"[cyan]Running trigger tests[/cyan] [{current}/{total}]: {test_name}")

        status.update("[cyan]Loading trigger tests...[/cyan]")
        report = evaluator.evaluate(
            skill_path,
            type_filter=trigger_type,
            progress_callback=update_progress,
        )

    # Output results
    if format == OutputFormat.json:
        report_json = json_module.dumps(report.to_dict(), indent=2)
        if output:
            output.write_text(report_json)
            console.print(f"Report written to: {output}")
        else:
            console.print(report_json)
    else:
        _print_trigger_report(report)

    if not report.overall_pass:
        raise typer.Exit(code=1)
