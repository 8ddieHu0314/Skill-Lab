"""CLI interface for skill-lab."""

from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from skill_lab import __version__
from skill_lab.core.models import EvalDimension, TraceReport, TriggerReport, TriggerType
from skill_lab.core.registry import registry
from skill_lab.evaluators.static_evaluator import StaticEvaluator
from skill_lab.evaluators.trace_evaluator import TraceEvaluator
from skill_lab.reporters.console_reporter import ConsoleReporter
from skill_lab.reporters.json_reporter import JsonReporter
from skill_lab.triggers.trigger_evaluator import TriggerEvaluator

app = typer.Typer(
    name="sklab",
    help="Agent Skills Evaluation Framework",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"sklab {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def app_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Evaluate agent skills through static analysis and quality checks."""
    pass


class OutputFormat(str, Enum):
    """Output format options."""

    json = "json"
    console = "console"


@app.command()
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
) -> None:
    """Evaluate a skill and generate a quality report."""
    # Resolve default path and validate
    skill_path = Path.cwd() if skill_path is None else skill_path.resolve()

    if not skill_path.exists():
        console.print(f"[red]Error: Path does not exist: {skill_path}[/red]")
        raise typer.Exit(code=1)
    if not skill_path.is_dir():
        console.print(f"[red]Error: Path is not a directory: {skill_path}[/red]")
        raise typer.Exit(code=1)
    if not (skill_path / "SKILL.md").exists():
        console.print(f"[red]Error: No SKILL.md found in {skill_path}[/red]")
        console.print("[dim]This directory does not appear to be a skill folder.[/dim]")
        raise typer.Exit(code=1)

    try:
        evaluator = StaticEvaluator(spec_only=spec_only)
        report = evaluator.evaluate(skill_path)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from None

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

    # Exit with non-zero code if validation failed
    if not report.overall_pass:
        raise typer.Exit(code=1)


@app.command()
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
    """Quick validation that reports only errors."""
    # Resolve default path and validate
    skill_path = Path.cwd() if skill_path is None else skill_path.resolve()

    if not skill_path.exists():
        console.print(f"[red]Error: Path does not exist: {skill_path}[/red]")
        raise typer.Exit(code=1)
    if not skill_path.is_dir():
        console.print(f"[red]Error: Path is not a directory: {skill_path}[/red]")
        raise typer.Exit(code=1)
    if not (skill_path / "SKILL.md").exists():
        console.print(f"[red]Error: No SKILL.md found in {skill_path}[/red]")
        console.print("[dim]This directory does not appear to be a skill folder.[/dim]")
        raise typer.Exit(code=1)

    try:
        evaluator = StaticEvaluator(spec_only=spec_only)
        passed, errors = evaluator.validate(skill_path)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from None

    if passed:
        console.print("[green]Validation passed![/green]")
    else:
        console.print("[red]Validation failed![/red]")
        console.print()
        for error in errors:
            console.print(f"  [red]X[/red] [{error.check_id}] {error.message}")
        console.print()
        raise typer.Exit(code=1)


@app.command("list-checks")
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

    severity_styles = {
        "error": "red",
        "warning": "yellow",
        "info": "blue",
    }

    for check_class in sorted(checks, key=lambda c: c.check_id):
        severity_style = severity_styles.get(check_class.severity.value, "white")
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
    console.print(f"\nTotal: {len(checks)} checks ({spec_count} spec-required, {len(checks) - spec_count} quality suggestions)")


@app.command("trigger")
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
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Only show failed tests, no analysis (for CI/scripting)",
        ),
    ] = False,
) -> None:
    """Run trigger tests to verify skill activation.

    Tests whether the skill activates correctly for different prompt types:
    - explicit: Skill named directly with $ prefix
    - implicit: Describes exact scenario without naming skill
    - contextual: Realistic noisy prompt with domain context
    - negative: Should NOT trigger (catches false positives)

    Requires test definitions in tests/scenarios.yaml or tests/triggers.yaml.
    """
    # Resolve default path and validate
    skill_path = Path.cwd() if skill_path is None else skill_path.resolve()

    if not skill_path.exists():
        console.print(f"[red]Error: Path does not exist: {skill_path}[/red]")
        raise typer.Exit(code=1)
    if not skill_path.is_dir():
        console.print(f"[red]Error: Path is not a directory: {skill_path}[/red]")
        raise typer.Exit(code=1)
    if not (skill_path / "SKILL.md").exists():
        console.print(f"[red]Error: No SKILL.md found in {skill_path}[/red]")
        console.print("[dim]This directory does not appear to be a skill folder.[/dim]")
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
    evaluator = TriggerEvaluator(runtime=runtime, analyze_failures=not quiet)

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
        import json as json_module
        report_json = json_module.dumps(report.to_dict(), indent=2)
        if output:
            output.write_text(report_json)
            console.print(f"Report written to: {output}")
        else:
            console.print(report_json)
    else:
        _print_trigger_report(report, quiet=quiet)

    # Exit with non-zero code if tests failed
    if not report.overall_pass:
        raise typer.Exit(code=1)


def _format_duration(ms: float) -> str:
    """Format duration in human-readable form."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.1f}s"


def _print_trigger_report(report: TriggerReport, quiet: bool = False) -> None:
    """Print a trigger test report to console.

    Args:
        report: The trigger test report to print.
        quiet: If True, only show failed tests without analysis.
    """
    # Quiet mode: minimal output for CI/scripting
    if quiet:
        _print_trigger_report_quiet(report)
        return

    # Full output mode
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
        f"[dim]Runtime:[/dim] {report.runtime} [dim]│[/dim] "
        f"[dim]Duration:[/dim] {duration} [dim]│[/dim] "
        f"{pass_status}"
    )
    console.print()

    # Results table with borders
    table = Table(box=box.ROUNDED, padding=(0, 1))
    table.add_column("Test", style="cyan", no_wrap=True)
    table.add_column("Type", style="dim")
    table.add_column("Status", justify="center")  # Status column

    for result in report.results:
        status = "[green]✓[/green]" if result.passed else "[red]✗[/red]"
        table.add_row(
            result.test_name,
            result.trigger_type.value,
            status,
        )

    console.print(table)
    console.print()

    # Failure analysis section
    failed_with_analysis = [
        r for r in report.results if not r.passed and r.failure_analysis
    ]
    if failed_with_analysis:
        console.print(f"[bold red]Failures ({len(failed_with_analysis)}):[/bold red]")
        console.print()

        for result in failed_with_analysis:
            analysis = result.failure_analysis
            assert analysis is not None  # for type checker

            # Test header with expected vs actual
            expected = "trigger" if result.expected_trigger else "no_trigger"
            actual = "trigger" if result.skill_triggered else "no_trigger"
            console.print(f"  [red]✗[/red] [bold]{result.test_name}[/bold]")
            console.print(f"    [dim]Expected:[/dim] {expected} [dim]│[/dim] [dim]Got:[/dim] {actual}")
            console.print()

            # Analysis
            console.print(f"    [dim]Analysis:[/dim] {analysis.analysis}")

            # Keywords on separate line if present
            if analysis.matching_keywords:
                keywords = ", ".join(analysis.matching_keywords[:5])
                console.print(f"    [dim]Keywords:[/dim] {keywords}")

            console.print()

            # Suggestions with clear visual hierarchy
            if analysis.suggestions:
                if analysis.is_likely_test_bug:
                    console.print("    [yellow]⚠ Test bug likely[/yellow]")
                console.print("    [bold]Suggestions:[/bold]")
                for suggestion in analysis.suggestions:
                    # Confidence badge
                    if suggestion.confidence >= 0.7:
                        badge = "[black on green] HIGH [/black on green]"
                    elif suggestion.confidence >= 0.4:
                        badge = "[black on yellow] MED [/black on yellow]"
                    else:
                        badge = "[white on dim] LOW [/white on dim]"

                    console.print(f"      {badge} {suggestion.description}")
                    if suggestion.code_snippet:
                        console.print(f"           [dim]{suggestion.code_snippet}[/dim]")

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
        console.print("[dim]By type:[/dim] " + " [dim]│[/dim] ".join(parts))
        console.print()


def _print_trigger_report_quiet(report: TriggerReport) -> None:
    """Print minimal trigger report for CI/scripting."""
    console.print()
    if report.overall_pass:
        console.print(f"[green]✓ {report.tests_passed}/{report.tests_run} passed[/green]")
    else:
        console.print(f"[red]✗ {report.tests_passed}/{report.tests_run} passed[/red]")
        for result in report.results:
            if not result.passed:
                expected = "trigger" if result.expected_trigger else "no_trigger"
                actual = "trigger" if result.skill_triggered else "no_trigger"
                console.print(f"  {result.test_name}: expected {expected}, got {actual}")
    console.print()


@app.command("eval-trace", hidden=True)
def eval_trace(
    skill_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the skill directory",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    trace: Annotated[
        Path,
        typer.Option(
            "--trace",
            "-t",
            help="Path to the JSONL trace file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
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
    """Evaluate a trace against YAML-defined trace checks.

    Runs checks defined in tests/trace_checks.yaml against the provided
    execution trace file. Supports check types:
    - command_presence: Verify specific commands were run
    - file_creation: Check if files were created
    - event_sequence: Verify commands in correct order
    - loop_detection: Detect excessive command repetition
    - efficiency: Check command count limits
    """
    try:
        evaluator = TraceEvaluator()
        report = evaluator.evaluate(skill_path, trace)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from None
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from None

    # Output results
    if format == OutputFormat.json:
        import json as json_module

        report_json = json_module.dumps(report.to_dict(), indent=2)
        if output:
            output.write_text(report_json)
            console.print(f"Report written to: {output}")
        else:
            console.print(report_json)
    else:
        _print_trace_report(report)

    # Exit with non-zero code if checks failed
    if not report.overall_pass:
        raise typer.Exit(code=1)


def _print_trace_report(report: TraceReport) -> None:
    """Print a trace evaluation report to console."""
    from rich.panel import Panel
    from rich.table import Table

    # Header
    console.print()
    console.print(
        Panel(
            f"[bold]Trace:[/bold] {report.trace_path}\n"
            f"[bold]Project:[/bold] {report.project_dir}",
            title="Trace Evaluation Report",
            border_style="blue",
        )
    )

    # Summary
    console.print()
    if report.overall_pass:
        console.print(f"[green]All {report.checks_passed} checks passed![/green]")
    else:
        console.print(
            f"[red]{report.checks_failed} of {report.checks_run} checks failed[/red]"
        )
    console.print(f"Pass rate: {report.pass_rate:.1f}%")
    console.print()

    # Results table
    table = Table(title="Check Results")
    table.add_column("Status", width=6)
    table.add_column("Check ID", style="cyan", width=25)
    table.add_column("Type", style="blue", width=18)
    table.add_column("Message", width=50)

    for result in report.results:
        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        table.add_row(
            status,
            result.check_id,
            result.check_type,
            result.message,
        )

    console.print(table)
    console.print()

    # Summary by type
    if report.summary.get("by_type"):
        console.print("[bold]Summary by Check Type:[/bold]")
        for type_name, stats in report.summary["by_type"].items():
            passed = stats["passed"]
            total = stats["total"]
            pct = (passed / total * 100) if total > 0 else 0
            color = "green" if passed == total else "yellow" if passed > 0 else "red"
            console.print(f"  {type_name}: [{color}]{passed}/{total} ({pct:.0f}%)[/{color}]")
        console.print()

    console.print(f"Duration: {report.duration_ms:.1f}ms")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
