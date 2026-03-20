"""Console reporter for evaluation results using rich."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from skill_lab.core.colors import (
    ACCENT,
    BORDER,
    FAIL_COLOR,
    NEUTRAL_COLOR,
    PASS_COLOR,
    SECONDARY,
    SEVERITY_STYLES,
    WARN_COLOR,
)
from skill_lab.core.models import EvaluationReport, Severity, TraceReport


def score_color(score: float) -> str:
    """Return a rich color name based on a 0-100 quality score."""
    if score >= 80:
        return PASS_COLOR
    if score >= 60:
        return WARN_COLOR
    return FAIL_COLOR


class ConsoleReporter:
    """Reporter that outputs evaluation results to the console."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize the reporter.

        Args:
            verbose: If True, show all checks. If False, show only failures.
        """
        self.verbose = verbose
        self.console = Console()

    def _severity_style(self, severity: Severity) -> str:
        """Get the rich style for a severity level."""
        return SEVERITY_STYLES.get(severity.value, NEUTRAL_COLOR)

    def _print_verbose_hint(self, total_count: int, shown_count: int) -> None:
        """Print a hint about hidden passing checks when not in verbose mode."""
        if self.verbose:
            return
        hidden = total_count - shown_count
        if hidden > 0:
            self.console.print(
                f"[dim]({hidden} passing checks hidden, run [bold]sklab evaluate --verbose ./skill[/bold] to see all)[/dim]"
            )
        elif shown_count == 0:
            self.console.print(f"[{PASS_COLOR}]All checks passed![/{PASS_COLOR}]")
            self.console.print(
                "[dim](run [bold]sklab evaluate --verbose ./skill[/bold] to see details)[/dim]"
            )

    def report(self, report: EvaluationReport) -> None:
        """Print an evaluation report to the console.

        Args:
            report: The evaluation report to print.
        """
        # Header
        skill_name = report.skill_name or "Unknown"
        self.console.print()
        self.console.print(
            Panel(
                f"[bold]Skill:[/bold] {skill_name}\n[bold]Path:[/bold] {report.skill_path}",
                title="Skill Lab Evaluation",
                border_style=BORDER,
            )
        )

        # Score and status
        sc = score_color(report.quality_score)
        status = (
            f"[{PASS_COLOR}]PASS[/{PASS_COLOR}]"
            if report.overall_pass
            else f"[{FAIL_COLOR}]FAIL[/{FAIL_COLOR}]"
        )

        self.console.print()
        self.console.print(
            f"[bold]Quality Score:[/bold] [{sc}]{report.quality_score:.1f}/100[/{sc}]"
        )
        self.console.print(f"[bold]Status:[/bold] {status}")
        self.console.print(
            f"[bold]Checks:[/bold] {report.checks_passed}/{report.checks_run} passed"
        )
        self.console.print(f"[bold]Duration:[/bold] {report.duration_ms:.1f}ms")

        # Results table
        self.console.print()

        # Filter results based on verbosity
        results_to_show = (
            report.results if self.verbose else [r for r in report.results if not r.passed]
        )

        if results_to_show:
            table = Table(title="Check Results" if self.verbose else "Failed Checks")
            table.add_column("", width=4, no_wrap=True)
            table.add_column("Severity", min_width=6, no_wrap=True)
            table.add_column("Check", min_width=20)
            table.add_column("Message")

            for result in results_to_show:
                status_icon = (
                    f"[{PASS_COLOR}]OK[/{PASS_COLOR}]"
                    if result.passed
                    else f"[{self._severity_style(result.severity)}]X[/{self._severity_style(result.severity)}]"
                )
                severity_text = Text(
                    result.severity.value.upper(),
                    style=self._severity_style(result.severity),
                )
                display_message = result.message
                if not result.passed and result.fix:
                    display_message = f"{result.message}\n[dim]Fix: {result.fix}[/dim]"
                table.add_row(
                    status_icon,
                    severity_text,
                    result.check_id,
                    display_message,
                )

            self.console.print(table)

        self._print_verbose_hint(len(report.results), len(results_to_show))

        # Summary by dimension
        self.console.print()
        self.console.print("[bold]Summary by Dimension:[/bold]")
        for dim, counts in report.summary.get("by_dimension", {}).items():
            passed = counts.get("passed", 0)
            failed = counts.get("failed", 0)
            total = passed + failed
            if total > 0:
                color = PASS_COLOR if failed == 0 else WARN_COLOR if failed < passed else FAIL_COLOR
                self.console.print(f"  {dim}: [{color}]{passed}/{total} passed[/{color}]")

        self.console.print()

    def report_trace(self, report: TraceReport) -> None:
        """Print a trace evaluation report to the console.

        Args:
            report: The trace report to print.
        """
        # Header
        self.console.print()
        self.console.print(
            Panel(
                f"[bold]Trace:[/bold] {report.trace_path}\n"
                f"[bold]Project:[/bold] {report.project_dir}",
                title="Trace Evaluation Report",
                border_style=BORDER,
            )
        )

        # Summary
        self.console.print()
        if report.overall_pass:
            self.console.print(
                f"[{PASS_COLOR}]All {report.checks_passed} checks passed![/{PASS_COLOR}]"
            )
        else:
            self.console.print(
                f"[{FAIL_COLOR}]{report.checks_failed} of {report.checks_run} checks failed[/{FAIL_COLOR}]"
            )
        self.console.print(f"Pass rate: {report.pass_rate:.1f}%")
        self.console.print()

        # Results table
        results_to_show = (
            report.results if self.verbose else [r for r in report.results if not r.passed]
        )

        if results_to_show:
            table = Table(title="Check Results" if self.verbose else "Failed Checks")
            table.add_column("", width=4, no_wrap=True)
            table.add_column("Check ID", style=ACCENT, min_width=20)
            table.add_column("Type", style=SECONDARY, min_width=10, no_wrap=True)
            table.add_column("Message")

            for result in results_to_show:
                status = (
                    f"[{PASS_COLOR}]PASS[/{PASS_COLOR}]"
                    if result.passed
                    else f"[{FAIL_COLOR}]FAIL[/{FAIL_COLOR}]"
                )
                table.add_row(
                    status,
                    result.check_id,
                    result.check_type,
                    result.message,
                )

            self.console.print(table)

        self._print_verbose_hint(len(report.results), len(results_to_show))
        self.console.print()

        # Summary by type
        if report.summary.get("by_type"):
            self.console.print("[bold]Summary by Check Type:[/bold]")
            for type_name, stats in report.summary["by_type"].items():
                passed = stats["passed"]
                total = stats["total"]
                pct = (passed / total * 100) if total > 0 else 0
                color = PASS_COLOR if passed == total else WARN_COLOR if passed > 0 else FAIL_COLOR
                self.console.print(
                    f"  {type_name}: [{color}]{passed}/{total} ({pct:.0f}%)[/{color}]"
                )
            self.console.print()

        self.console.print(f"Duration: {report.duration_ms:.1f}ms")
        self.console.print()
