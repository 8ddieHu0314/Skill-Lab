"""CLI interface for skill-lab."""

from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from skill_lab.core.models import EvalDimension
from skill_lab.core.registry import registry
from skill_lab.evaluators.static_evaluator import StaticEvaluator
from skill_lab.reporters.console_reporter import ConsoleReporter
from skill_lab.reporters.json_reporter import JsonReporter

app = typer.Typer(
    name="skill-lab",
    help="Evaluate agent skills through static analysis and quality checks.",
    add_completion=False,
)
console = Console()


class OutputFormat(str, Enum):
    """Output format options."""

    json = "json"
    console = "console"


@app.command()
def evaluate(
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
    output: Annotated[
        Optional[Path],
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
            "-v",
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
    evaluator = StaticEvaluator(spec_only=spec_only)
    report = evaluator.evaluate(skill_path)

    if format == OutputFormat.json:
        reporter = JsonReporter()
        if output:
            reporter.write_file(report, output)
            console.print(f"Report written to: {output}")
        else:
            console.print(reporter.format(report))
    else:
        reporter = ConsoleReporter(verbose=verbose)
        reporter.report(report)

    # Exit with non-zero code if validation failed
    if not report.overall_pass:
        raise typer.Exit(code=1)


@app.command()
def validate(
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
    evaluator = StaticEvaluator(spec_only=spec_only)
    passed, errors = evaluator.validate(skill_path)

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
        Optional[str],
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
            raise typer.Exit(code=1)
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


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
