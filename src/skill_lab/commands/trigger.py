"""Trigger test command."""

import json as json_module
import time
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
from skill_lab.core.colors import ACCENT, FAIL_COLOR, PASS_COLOR, SECONDARY, WARN_COLOR
from skill_lab.core.constants import TESTS_DIR, TRACES_DIR
from skill_lab.core.models import TriggerReport, TriggerType
from skill_lab.core.telemetry import push_telemetry_extra
from skill_lab.triggers.test_loader import load_trigger_tests
from skill_lab.triggers.trigger_evaluator import TriggerEvaluator

TYPE_DESCRIPTIONS = {
    "explicit": "skill named directly with $ prefix",
    "implicit": "scenario described without naming the skill",
    "contextual": "realistic noisy prompt with domain context",
    "negative": "should NOT trigger — catches false positives",
}

CACHE_TTL_SECONDS = 300  # Anthropic prompt cache TTL (~5 min)


def _cache_is_warm(skill_path: Path) -> bool:
    traces_dir = skill_path / TRACES_DIR
    if not traces_dir.exists():
        return False
    cutoff = time.time() - CACHE_TTL_SECONDS
    return any(f.stat().st_mtime > cutoff for f in traces_dir.glob("*.jsonl"))


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
        f"[{PASS_COLOR}]{report.tests_passed}/{report.tests_run} passed[/{PASS_COLOR}]"
        if report.overall_pass
        else f"[{FAIL_COLOR}]{report.tests_passed}/{report.tests_run} passed[/{FAIL_COLOR}]"
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
    table.add_column("Test", style=ACCENT, no_wrap=True)
    table.add_column("Type", style="dim")
    table.add_column("Status", justify="center")  # Status column

    for result in report.results:
        status = (
            f"[{PASS_COLOR}]\u2713[/{PASS_COLOR}]"
            if result.passed
            else f"[{FAIL_COLOR}]\u2717[/{FAIL_COLOR}]"
        )
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
            color = PASS_COLOR if passed == total else WARN_COLOR if passed > 0 else FAIL_COLOR
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
        console.print(f"[{WARN_COLOR}]No trigger tests found.[/{WARN_COLOR}]")
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
            console.print(f"[{FAIL_COLOR}]Invalid trigger type: {type_filter}[/{FAIL_COLOR}]")
            console.print(f"Valid types: {', '.join(t.value for t in TriggerType)}")
            raise typer.Exit(code=1) from None

    # Load tests upfront for type legend + time estimate
    preview_cases, _ = load_trigger_tests(skill_path)
    if trigger_type:
        preview_cases = [tc for tc in preview_cases if tc.trigger_type == trigger_type]

    if preview_cases:
        types_present = dict.fromkeys(tc.trigger_type.value for tc in preview_cases)
        console.print("[bold]Trigger types:[/bold]")
        for t in types_present:
            console.print(f"  [{SECONDARY}]{t:<12}[/{SECONDARY}] {TYPE_DESCRIPTIONS[t]}")
        console.print()

    n = len(preview_cases)
    warm = _cache_is_warm(skill_path)
    per_test = 2 if warm else 60  # seconds: ~2s cached, ~60s cold
    est_seconds = n * per_test
    est_str = f"~{est_seconds}s" if est_seconds < 60 else f"~{est_seconds // 60} min"
    cache_hint = "cache warm" if warm else "cache cold"
    console.print(
        f"[dim]Running {n} test{'s' if n != 1 else ''} — estimated time: "
        f"{est_str} ({cache_hint})[/dim]\n"
    )

    # Run evaluation with progress display
    evaluator = TriggerEvaluator(runtime=runtime)

    with console.status("", spinner="dots") as status:

        def update_progress(current: int, total: int, test_name: str) -> None:
            status.update(
                f"[{ACCENT}]Running trigger tests[/{ACCENT}] [{current}/{total}]: {test_name}"
            )

        status.update(f"[{ACCENT}]Loading trigger tests...[/{ACCENT}]")
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
