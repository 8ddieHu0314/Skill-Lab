"""Console reporter for evaluation results using rich."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent_skills_eval.core.models import EvaluationReport, Severity


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
                title="Agent Skills Evaluation",
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
        elif not self.verbose:
            self.console.print("[green]All checks passed![/green]")

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
