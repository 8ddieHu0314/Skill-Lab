"""Console reporter for evaluation results using rich."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from skill_lab.core.llm import GenerationUsage
from skill_lab.core.models import EvaluationReport, JudgeResult, Severity, TraceReport

# Shared severity display mappings — keyed by Severity.value string
SEVERITY_STYLES: dict[str, str] = {
    "high": "bold red",
    "medium": "yellow",
    "low": "blue",
}


def score_color(score: float) -> str:
    """Return a rich color name based on a 0-100 quality score."""
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    return "red"


def _score_bar(score: int) -> str:
    """Render a 0-4 score as a colored visual bar."""
    filled = score
    empty = 4 - score
    if score >= 3:
        color = "green"
    elif score >= 2:
        color = "yellow"
    else:
        color = "red"
    filled_bar = "\u2588" * filled
    empty_bar = "\u2591" * empty
    return f"[{color}]{filled_bar}{empty_bar}[/{color}] {score}/4"


def _verdict_color(verdict: str) -> str:
    """Return a rich color for a verdict label."""
    if verdict == "Excellent":
        return "bold green"
    if verdict == "Good":
        return "green"
    if verdict == "Needs work":
        return "yellow"
    return "red"


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
        return SEVERITY_STYLES.get(severity.value, "white")

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
            self.console.print("[green]All checks passed![/green]")
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
                border_style="blue",
            )
        )

        # Score and status
        sc = score_color(report.quality_score)
        status = "[green]PASS[/green]" if report.overall_pass else "[red]FAIL[/red]"

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
                    "[green]OK[/green]"
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
                color = "green" if failed == 0 else "yellow" if failed < passed else "red"
                self.console.print(f"  {dim}: [{color}]{passed}/{total} passed[/{color}]")

        self.console.print()

    def report_judge(
        self,
        result: JudgeResult,
        usage: GenerationUsage | None = None,
    ) -> None:
        """Print LLM judge results to the console."""
        self.console.print()
        self.console.print(
            "[bold]LLM Quality Review[/bold]",
            style="on default",
        )

        axes = [
            ("activation", "Activation Quality", result.activation_score),
            ("instruction", "Instruction Quality", result.instruction_score),
        ]

        for axis_id, axis_label, axis_score in axes:
            axis_criteria = [c for c in result.criteria if c.axis == axis_id]

            self.console.print()
            table = Table(
                title=f"{axis_label} ({axis_score:.0f}%)",
                show_header=True,
            )
            table.add_column("Criterion", min_width=20)
            table.add_column("Score", justify="center", width=12)
            if self.verbose:
                table.add_column("Reasoning")

            for c in axis_criteria:
                bar = _score_bar(c.score)
                row: list[str] = [c.name, bar]
                if self.verbose:
                    row.append(f"[dim]{c.reasoning}[/dim]")
                table.add_row(*row)

            self.console.print(table)

        # Combined score and verdict
        jsc = score_color(result.judge_score)
        vc = _verdict_color(result.verdict)
        self.console.print()
        self.console.print(
            f"[bold]Judge Score:[/bold] [{jsc}]{result.judge_score:.1f}/100[/{jsc}]  "
            f"[{vc}]{result.verdict}[/{vc}]"
        )

        # Suggestions
        if result.suggestions:
            self.console.print()
            self.console.print("[bold]Suggestions:[/bold]")
            for i, suggestion in enumerate(result.suggestions, 1):
                self.console.print(f"  {i}. {suggestion}")

        if usage is not None:
            cost_str = f" (${usage.total_cost:.4f})" if usage.has_pricing else " (no pricing data)"
            self.console.print(
                f"\n[dim]Tokens:[/dim] {usage.input_tokens:,} in + "
                f"{usage.output_tokens:,} out = {usage.total_tokens:,}{cost_str}"
            )

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
        results_to_show = (
            report.results if self.verbose else [r for r in report.results if not r.passed]
        )

        if results_to_show:
            table = Table(title="Check Results" if self.verbose else "Failed Checks")
            table.add_column("", width=4, no_wrap=True)
            table.add_column("Check ID", style="cyan", min_width=20)
            table.add_column("Type", style="blue", min_width=10, no_wrap=True)
            table.add_column("Message")

            for result in results_to_show:
                status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
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
                color = "green" if passed == total else "yellow" if passed > 0 else "red"
                self.console.print(
                    f"  {type_name}: [{color}]{passed}/{total} ({pct:.0f}%)[/{color}]"
                )
            self.console.print()

        self.console.print(f"Duration: {report.duration_ms:.1f}ms")
        self.console.print()
