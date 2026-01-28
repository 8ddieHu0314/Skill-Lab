"""Console reporter for evaluation results using rich."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from skill_lab.core.models import EvaluationReport, Severity, TraceReport


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
        styles = {
            Severity.ERROR: "bold red",
            Severity.WARNING: "yellow",
            Severity.INFO: "blue",
        }
        return styles.get(severity, "white")

    def _severity_icon(self, severity: Severity) -> str:
        """Get the icon for a severity level."""
        icons = {
            Severity.ERROR: "X",
            Severity.WARNING: "!",
            Severity.INFO: "i",
        }
        return icons.get(severity, "?")

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
                f"[bold]Skill:[/bold] {skill_name}\n"
                f"[bold]Path:[/bold] {report.skill_path}",
                title="Skill Lab Evaluation",
                border_style="blue",
            )
        )

        # Score and status
        score_color = "green" if report.quality_score >= 80 else "yellow" if report.quality_score >= 60 else "red"
        status = "[green]PASS[/green]" if report.overall_pass else "[red]FAIL[/red]"

        self.console.print()
        self.console.print(f"[bold]Quality Score:[/bold] [{score_color}]{report.quality_score:.1f}/100[/{score_color}]")
        self.console.print(f"[bold]Status:[/bold] {status}")
        self.console.print(f"[bold]Checks:[/bold] {report.checks_passed}/{report.checks_run} passed")
        self.console.print(f"[bold]Duration:[/bold] {report.duration_ms:.1f}ms")

        # Results table
        self.console.print()

        # Filter results based on verbosity
        results_to_show = report.results if self.verbose else [r for r in report.results if not r.passed]

        if results_to_show:
            table = Table(title="Check Results" if self.verbose else "Failed Checks")
            table.add_column("Status", width=6)
            table.add_column("Severity", width=8)
            table.add_column("Check", width=30)
            table.add_column("Message", width=50)

            for result in results_to_show:
                status_icon = "[green]OK[/green]" if result.passed else f"[{self._severity_style(result.severity)}]{self._severity_icon(result.severity)}[/{self._severity_style(result.severity)}]"
                severity_text = Text(result.severity.value.upper(), style=self._severity_style(result.severity))
                table.add_row(
                    status_icon,
                    severity_text,
                    result.check_id,
                    result.message,
                )

            self.console.print(table)

        # Show verbose hint when not in verbose mode
        if not self.verbose:
            hidden_count = len(report.results) - len(results_to_show)
            if hidden_count > 0:
                self.console.print(f"[dim]({hidden_count} passing checks hidden, run with --verbose to see all)[/dim]")
            elif not results_to_show:
                self.console.print("[green]All checks passed![/green]")
                self.console.print("[dim](run with --verbose to see details)[/dim]")

        # Summary by dimension
        self.console.print()
        self.console.print("[bold]Summary by Dimension:[/bold]")
        for dim, counts in report.summary.get("by_dimension", {}).items():
            passed = counts.get("passed", 0)
            failed = counts.get("failed", 0)
            total = passed + failed
            if total > 0:
                color = "green" if failed == 0 else "yellow" if failed < passed else "red"
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
                border_style="blue",
            )
        )

        # Summary
        self.console.print()
        if report.overall_pass:
            self.console.print(f"[green]All {report.checks_passed} checks passed![/green]")
        else:
            self.console.print(
                f"[red]{report.checks_failed} of {report.checks_run} checks failed[/red]"
            )
        self.console.print(f"Pass rate: {report.pass_rate:.1f}%")
        self.console.print()

        # Results table
        results_to_show = report.results if self.verbose else [r for r in report.results if not r.passed]

        if results_to_show:
            table = Table(title="Check Results" if self.verbose else "Failed Checks")
            table.add_column("Status", width=6)
            table.add_column("Check ID", style="cyan", width=25)
            table.add_column("Type", style="blue", width=18)
            table.add_column("Message", width=50)

            for result in results_to_show:
                status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
                table.add_row(
                    status,
                    result.check_id,
                    result.check_type,
                    result.message,
                )

            self.console.print(table)

        # Show verbose hint when not in verbose mode
        if not self.verbose:
            hidden_count = len(report.results) - len(results_to_show)
            if hidden_count > 0:
                self.console.print(f"[dim]({hidden_count} passing checks hidden, run with --verbose to see all)[/dim]")
            elif not results_to_show:
                self.console.print("[green]All checks passed![/green]")
                self.console.print("[dim](run with --verbose to see details)[/dim]")
        self.console.print()

        # Summary by type
        if report.summary.get("by_type"):
            self.console.print("[bold]Summary by Check Type:[/bold]")
            for type_name, stats in report.summary["by_type"].items():
                passed = stats["passed"]
                total = stats["total"]
                pct = (passed / total * 100) if total > 0 else 0
                color = "green" if passed == total else "yellow" if passed > 0 else "red"
                self.console.print(f"  {type_name}: [{color}]{passed}/{total} ({pct:.0f}%)[/{color}]")
            self.console.print()

        self.console.print(f"Duration: {report.duration_ms:.1f}ms")
        self.console.print()
