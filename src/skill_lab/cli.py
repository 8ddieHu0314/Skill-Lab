"""CLI interface for skill-lab."""

import contextlib
import functools
import json as json_module
import os
import sys
import time
from collections.abc import Callable, Iterator
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from skill_lab import __version__
from skill_lab.core.constants import SKLAB_HOME, SKLAB_INITIALIZED, TESTS_DIR
from skill_lab.core.models import EvalDimension, TriggerReport, TriggerType
from skill_lab.core.registry import registry
from skill_lab.core.telemetry import (
    _pop_pending_error,
    _pop_telemetry_extras,
    _store_pending_error,
    check_for_update,
    compute_repo_root_hash,
    init_telemetry,
    push_telemetry_extra,
    record_error,
    record_event,
)
from skill_lab.core.tokens import estimate_tokens
from skill_lab.evaluators.static_evaluator import StaticEvaluator
from skill_lab.evaluators.trace_evaluator import TraceEvaluator
from skill_lab.parsers.skill_parser import parse_skill
from skill_lab.reporters.console_reporter import SEVERITY_LABELS, SEVERITY_STYLES, ConsoleReporter
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


def _maybe_first_run_scan() -> bool:
    """Return True if the first-run scan was executed, False if already initialized."""
    """On first ever `sklab` invocation, scan for skills and show a welcome evaluation.

    Discovery order:
      1. Git repo root (if inside a repo)
      2. ~/.claude/.skill/ (Claude-installed skills)
      3. Current working directory (fallback)

    Writes ~/.sklab/.initialized so this only runs once.
    """
    if SKLAB_INITIALIZED.exists():
        return False

    # Mark as initialized immediately so a crash mid-scan doesn't loop forever
    SKLAB_HOME.mkdir(parents=True, exist_ok=True)
    SKLAB_INITIALIZED.touch()

    # Discover roots in priority order, deduplicating
    cwd = Path.cwd()
    roots: list[Path] = []
    seen: set[Path] = set()

    repo_root = _find_repo_root(cwd)
    if repo_root and repo_root not in seen:
        roots.append(repo_root)
        seen.add(repo_root)

    claude_skills = Path.home() / ".claude" / ".skill"
    if claude_skills.exists() and claude_skills not in seen:
        roots.append(claude_skills)
        seen.add(claude_skills)

    if cwd not in seen:
        roots.append(cwd)
        seen.add(cwd)

    # Collect all skill paths across all roots
    skill_paths: list[Path] = []
    for root in roots:
        skill_paths.extend(_discover_skills(root))

    # Welcome banner
    console.print()
    console.print(
        Panel(
            "[bold]Welcome to sklab![/bold]\n\n"
            "Scanning for skills across your repo and installed skills...",
            expand=False,
            border_style="cyan",
        )
    )
    console.print()

    if not skill_paths:
        console.print("[yellow]No skills found in your repo or installed skills.[/yellow]")
        console.print()
        _print_getting_started()
        return True

    console.print(f"[dim]Found {len(skill_paths)} skill(s). Running initial evaluation...[/dim]\n")

    evaluator = StaticEvaluator()
    summary_rows: list[tuple[str, str, str, str]] = []

    for sp in skill_paths:
        try:
            report = evaluator.evaluate(sp)
        except Exception as e:
            console.print(f"[red]Error evaluating {sp.name}: {e}[/red]")
            continue

        ConsoleReporter(verbose=False).report(report)

        score_str = f"{report.quality_score:.1f}"
        status_str = "[green]PASS[/green]" if report.overall_pass else "[red]FAIL[/red]"
        skill_name = report.skill_name or sp.name
        try:
            rel_path = str(sp.relative_to(cwd))
        except ValueError:
            rel_path = str(sp)
        summary_rows.append((skill_name, rel_path, score_str, status_str))

    # Summary table
    console.print()
    table = Table(title=f"Initial Scan — {len(skill_paths)} skill(s)", box=box.ROUNDED)
    table.add_column("Skill", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Status", justify="center")
    for name, path, score, status in summary_rows:
        table.add_row(name, path, score, status)
    console.print(table)
    console.print()

    _print_getting_started()
    return True


def _print_getting_started() -> None:
    """Print a command reference guide. Shown after first-run scan and on every bare `sklab`."""
    guide = Table.grid(padding=(0, 2))
    guide.add_column(style="bold cyan", no_wrap=True)
    guide.add_column(style="dim")

    guide.add_row(
        "sklab evaluate [green]./my-skill[/green]", "Full quality evaluation (0–100 score)"
    )
    guide.add_row("  [dim]--verbose / -V[/dim]", "Show all checks, not just failures")
    guide.add_row("  [dim]--spec-only / -s[/dim]", "Only run the 10 spec-required checks")
    guide.add_row("  [dim]--all[/dim]", "Evaluate every skill in the current directory")
    guide.add_row("", "")
    guide.add_row(
        "sklab validate [green]./my-skill[/green]", "Quick pass/fail — exits 0 or 1 (great for CI)"
    )
    guide.add_row("  [dim]--spec-only / -s[/dim]", "Only validate against the Agent Skills spec")
    guide.add_row("  [dim]--all[/dim]", "Validate every skill in the current directory")
    guide.add_row("  [dim]--repo[/dim]", "Validate every skill from the git repo root")
    guide.add_row("", "")
    guide.add_row(
        "sklab scan [green]./my-skill[/green]", "Security scan — shows BLOCK / SUS / ALLOW status"
    )
    guide.add_row("  [dim]--all[/dim]", "Scan every skill in the current directory")
    guide.add_row("", "")
    guide.add_row("sklab list-checks", "Browse all 28 checks across 4 dimensions")
    guide.add_row("  [dim]--spec-only[/dim]", "Only spec-required checks")
    guide.add_row("  [dim]--suggestions-only[/dim]", "Only quality suggestions")
    guide.add_row("", "")
    guide.add_row("sklab stats", "Your personal usage history and score trends")
    guide.add_row("  [dim]count[/dim]", "Skill invocation counts for the current month")
    guide.add_row("  [dim]score[/dim]", "Score trend for all evaluated skills")
    guide.add_row("  [dim]tokens[/dim]", "Token usage per skill for the current month")
    guide.add_row("", "")
    guide.add_row("sklab", "Re-run this guide anytime")

    console.print(
        Panel(
            guide,
            title="[bold]Getting Started[/bold]",
            border_style="dim",
            expand=False,
        )
    )
    console.print()


@app.callback(invoke_without_command=True)
def app_callback(
    ctx: typer.Context,
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
    if ctx.invoked_subcommand is None and not _maybe_first_run_scan():
        _print_getting_started()


def _find_repo_root(start: Path) -> Path | None:
    """Walk up from start looking for a .git directory."""
    current = start.resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _discover_skills(root: Path) -> list[Path]:
    """Recursively find all skill directories (containing SKILL.md) under root.

    Skips hidden directories (dot-prefixed) to avoid .git, .claude, etc.
    """
    skills: list[Path] = []
    for path in sorted(root.rglob("SKILL.md")):
        # Skip hidden dirs in the path (e.g. .claude/.skill/...)
        if any(part.startswith(".") for part in path.parts):
            continue
        skills.append(path.parent)
    return skills


def _resolve_skill_path(skill_path: Path | None) -> Path:
    """Resolve and validate a skill directory path.

    Args:
        skill_path: User-provided path, or None for current directory.

    Returns:
        Resolved absolute path.

    Raises:
        typer.Exit: If path doesn't exist, isn't a directory, or has no SKILL.md.
    """
    resolved = Path.cwd() if skill_path is None else skill_path.resolve()
    if not resolved.exists():
        console.print(f"[red]Error: Path does not exist: {resolved}[/red]")
        raise typer.Exit(code=1)
    if not resolved.is_dir():
        console.print(f"[red]Error: Path is not a directory: {resolved}[/red]")
        raise typer.Exit(code=1)
    if not (resolved / "SKILL.md").exists():
        console.print(f"[red]Error: No SKILL.md found in {resolved}[/red]")
        console.print("[dim]This directory does not appear to be a skill folder.[/dim]")
        raise typer.Exit(code=1)
    return resolved


@contextlib.contextmanager
def _cli_error_handler() -> Iterator[None]:
    """Catch exceptions and convert to styled CLI error + exit code 1."""
    try:
        yield
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from None


def _record_telemetry(command: str, start: float, exit_code: int) -> None:
    duration_ms = (time.perf_counter() - start) * 1000
    extras = _pop_telemetry_extras()
    command_event_id: int | None = None
    with contextlib.suppress(Exception):
        command_event_id = record_event(command, duration_ms, exit_code, **extras)
    pending_err = _pop_pending_error()
    if pending_err is not None:
        with contextlib.suppress(Exception):
            record_error(pending_err, command, command_event_id)
    with contextlib.suppress(Exception):
        latest = check_for_update()
        if latest:
            print(
                f"\nsklab {latest} is available (you have {__version__}). "
                f"Run: pip install --upgrade skill-lab",
                file=sys.stderr,
            )


# Params treated as positional args — not captured as flags
_POSITIONAL_PARAMS = {"skill_path", "skill_paths", "trace"}


def _with_telemetry(command_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that wraps a CLI command with init + timing + event recording."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            init_telemetry()
            from skill_lab.core.setup import init_hooks_on_first_run

            init_hooks_on_first_run()

            # Capture boolean flags explicitly set to True
            flags = [
                f"--{k.replace('_', '-')}"
                for k, v in kwargs.items()
                if k not in _POSITIONAL_PARAMS and v is True
            ]
            if flags:
                push_telemetry_extra(flags=flags)

            start = time.perf_counter()
            exit_code = 0
            try:
                return fn(*args, **kwargs)
            except SystemExit as e:
                exit_code = e.code if isinstance(e.code, int) else 0
                raise
            except Exception as e:
                exit_code = 1
                _store_pending_error(e)
                raise
            finally:
                _record_telemetry(command_name, start, exit_code)

        return wrapper

    return decorator


class OutputFormat(str, Enum):
    """Output format options."""

    json = "json"
    console = "console"


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

    # Summary table
    if format == OutputFormat.console:
        console.print()
        table = Table(title=f"Summary — {len(skill_paths)} skill(s)", box=box.ROUNDED)
        table.add_column("Skill", style="cyan")
        table.add_column("Path", style="dim")
        table.add_column("Score", justify="right")
        table.add_column("Status", justify="center")
        for name, path, score, status in summary_rows:
            table.add_row(name, path, score, status)
        console.print(table)

    if any_failed:
        raise typer.Exit(code=1)


def _run_bulk_validate(roots: list[Path], spec_only: bool) -> None:
    """Discover and validate all skills under the given root directories."""
    skill_paths: list[Path] = []
    for root in roots:
        found = _discover_skills(root)
        skill_paths.extend(found)

    if not skill_paths:
        console.print("[yellow]No skill folders found (no SKILL.md files discovered).[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"[dim]Found {len(skill_paths)} skill(s). Running validate...[/dim]\n")

    evaluator = StaticEvaluator(spec_only=spec_only, include_security=True)
    any_failed = False
    summary_rows: list[tuple[str, str, str]] = []  # name, path, status

    for sp in skill_paths:
        with _cli_error_handler():
            passed, errors = evaluator.validate(sp)

        skill_name = sp.name
        rel_path = str(sp.relative_to(Path.cwd())) if sp.is_relative_to(Path.cwd()) else str(sp)

        if passed:
            status_str = "[green]PASS[/green]"
        else:
            status_str = "[red]FAIL[/red]"
            console.print(f"[bold]{skill_name}[/bold] ({rel_path})")
            for error in errors:
                console.print(f"  [red]X[/red] [{error.check_id}] {error.message}")
            has_security = any(e.check_id == "security.scan" for e in errors)
            has_other = any(e.check_id != "security.scan" for e in errors)
            if has_security and has_other:
                console.print(
                    f"  [dim]Run [bold]sklab evaluate {rel_path}[/bold] for full quality details "
                    f"or [bold]sklab scan {rel_path}[/bold] for security findings.[/dim]"
                )
            elif has_security:
                console.print(
                    f"  [dim]Run [bold]sklab scan {rel_path}[/bold] for full security findings.[/dim]"
                )
            else:
                console.print(
                    f"  [dim]Run [bold]sklab evaluate {rel_path}[/bold] for full details.[/dim]"
                )
            console.print()
            any_failed = True

        summary_rows.append((skill_name, rel_path, status_str))

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
) -> None:
    """Evaluate a skill and generate a quality report.

    Run from inside a skill directory, or pass the path as an argument.
    """
    if all_skills and skill_path is not None:
        console.print("[red]Error: Cannot combine --all with a skill path argument.[/red]")
        raise typer.Exit(code=1)

    if all_skills:
        _run_bulk_evaluate([Path.cwd()], verbose, spec_only, format)
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
    all_skills: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Discover and validate all skills in the current directory (recursive)",
        ),
    ] = False,
    repo: Annotated[
        bool,
        typer.Option(
            "--repo",
            help="Discover and validate all skills from the git repo root (recursive)",
        ),
    ] = False,
) -> None:
    """Quick validation that reports only errors."""
    if (all_skills or repo) and skill_path is not None:
        console.print("[red]Error: Cannot combine --all/--repo with a skill path argument.[/red]")
        raise typer.Exit(code=1)

    if all_skills and repo:
        console.print("[red]Error: --all and --repo are mutually exclusive.[/red]")
        raise typer.Exit(code=1)

    if all_skills:
        _run_bulk_validate([Path.cwd()], spec_only)
        return

    if repo:
        repo_root = _find_repo_root(Path.cwd())
        if repo_root is None:
            console.print("[red]Error: Not inside a git repository.[/red]")
            raise typer.Exit(code=1)
        console.print(f"[dim]Repo root: {repo_root}[/dim]")
        _run_bulk_validate([repo_root], spec_only)
        return

    skill_path = _resolve_skill_path(skill_path)

    with _cli_error_handler():
        evaluator = StaticEvaluator(spec_only=spec_only, include_security=True)
        passed, errors = evaluator.validate(skill_path)

    if passed:
        console.print("[green]Validation passed![/green]")
    else:
        console.print("[red]Validation failed![/red]")
        console.print()
        for error in errors:
            console.print(f"  [red]X[/red] [{error.check_id}] {error.message}")
        console.print()
        has_security = any(e.check_id == "security.scan" for e in errors)
        has_other = any(e.check_id != "security.scan" for e in errors)
        path_str = f" {skill_path}"
        if has_security and has_other:
            console.print(
                f"[dim]Run [bold]sklab evaluate{path_str}[/bold] for full quality details "
                f"or [bold]sklab scan{path_str}[/bold] for security findings.[/dim]"
            )
        elif has_security:
            console.print(
                f"[dim]Run [bold]sklab scan{path_str}[/bold] for full security findings.[/dim]"
            )
        else:
            console.print(
                f"[dim]Run [bold]sklab evaluate{path_str}[/bold] for full details.[/dim]"
            )
        console.print()
        raise typer.Exit(code=1)




def _run_bulk_scan(roots: list[Path]) -> None:
    """Discover and security-scan all skills under the given root directories."""
    from skill_lab.checks.static.security import SecurityScanCheck
    from skill_lab.parsers.skill_parser import parse_skill as _parse_skill

    skill_paths: list[Path] = []
    for root in roots:
        found = _discover_skills(root)
        skill_paths.extend(found)

    if not skill_paths:
        console.print("[yellow]No skill folders found (no SKILL.md files discovered).[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"[dim]Found {len(skill_paths)} skill(s). Running scan...[/dim]\n")

    check = SecurityScanCheck()
    any_blocked = False
    summary_rows: list[tuple[str, str, str]] = []  # name, path, status

    for sp in skill_paths:
        with _cli_error_handler():
            skill = _parse_skill(sp)

        result = check.run(skill)
        details = result.details or {}
        status: str = details.get("status", "allow")
        findings: list[dict[str, str]] = details.get("findings", [])
        skill_name = skill.metadata.name if skill.metadata else sp.name
        rel_path = str(sp.relative_to(Path.cwd())) if sp.is_relative_to(Path.cwd()) else str(sp)

        if status == "block":
            status_str = "[bold red]BLOCK[/bold red]"
            any_blocked = True
            console.print(f"[bold]{skill_name}[/bold] ({rel_path})")
            for f in findings:
                console.print(f"  [red]![/red] {f.get('problem', '')} — {f.get('text', '')}")
            console.print()
        elif status == "sus":
            status_str = "[bold yellow]SUS[/bold yellow]"
        else:
            status_str = "[bold green]ALLOW[/bold green]"

        summary_rows.append((skill_name, rel_path, status_str))

    console.print()
    table = Table(title=f"Security Summary — {len(skill_paths)} skill(s)", box=box.ROUNDED)
    table.add_column("Skill", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Status", justify="center")
    for name, path, status_str in summary_rows:
        table.add_row(name, path, status_str)
    console.print(table)

    if any_blocked:
        raise typer.Exit(code=1)


@app.command("scan")
@_with_telemetry("scan")
def scan(
    skill_path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the skill directory (defaults to current directory)",
        ),
    ] = None,
    all_skills: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Discover and scan all skills in the current directory (recursive)",
        ),
    ] = False,
) -> None:
    """Run the security scan and show detailed findings.

    Status:
      BLOCK — any injection, jailbreak, unicode obfuscation, YAML, or evaluator finding
      SUS   — size/structure anomalies only (oversized body, repeated tokens, etc.)
      ALLOW — no findings

    Exits 1 on BLOCK.
    """
    from skill_lab.checks.static.security import SecurityScanCheck

    if all_skills and skill_path is not None:
        console.print("[red]Error: Cannot combine --all with a skill path argument.[/red]")
        raise typer.Exit(code=1)

    if all_skills:
        _run_bulk_scan([Path.cwd()])
        return

    skill_path = _resolve_skill_path(skill_path)

    with _cli_error_handler():
        from skill_lab.parsers.skill_parser import parse_skill as _parse_skill

        skill = _parse_skill(skill_path)

    result = SecurityScanCheck().run(skill)
    details = result.details or {}
    status: str = details.get("status", "allow")
    findings: list[dict[str, str]] = details.get("findings", [])

    if status == "block":
        status_label = "[bold red]BLOCK[/bold red]"
        border = "red"
    elif status == "sus":
        status_label = "[bold yellow]SUS[/bold yellow]"
        border = "yellow"
    else:
        status_label = "[bold green]ALLOW[/bold green]"
        border = "green"

    skill_name = skill.metadata.name if skill.metadata else skill_path.name
    console.print()
    console.print(
        Panel(
            f"[bold]Skill:[/bold] {skill_name}\n[bold]Path:[/bold] {skill_path}",
            title="Security Scan",
            border_style=border,
        )
    )
    console.print()
    console.print(f"[bold]Status:[/bold]  {status_label}")
    console.print()

    if findings:
        table = Table(title="Findings", box=box.SIMPLE_HEAD)
        table.add_column("Location", style="dim", no_wrap=True)
        table.add_column("Problem")
        table.add_column("Text", style="dim")
        for f in findings:
            table.add_row(
                f.get("location", ""),
                f.get("problem", ""),
                f.get("text", ""),
            )
        console.print(table)
    else:
        console.print("[green]No security findings.[/green]")

    console.print()

    if status == "block":
        raise typer.Exit(code=1)

@app.command("list-checks")
def list_checks(
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
    if spec_only:
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
            f"[{severity_style}]{SEVERITY_LABELS.get(check_class.severity.value, check_class.severity.value)}[/{severity_style}]",
            spec_badge,
            check_class.description,
        )

    console.print(table)
    spec_count = sum(1 for c in checks if c.spec_required)
    console.print(
        f"\nTotal: {len(checks)} checks ({spec_count} spec-required, {len(checks) - spec_count} quality suggestions)"
    )


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

    Requires test definitions in .skill-lab/tests/scenarios.yaml or .skill-lab/tests/triggers.yaml.
    """
    skill_path = _resolve_skill_path(skill_path)

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
            f".skill-lab/tests/triggers.yaml[/dim]"
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


@app.command("generate")
@_with_telemetry("generate")
def generate(
    skill_path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the skill directory (defaults to current directory)",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help="Anthropic model ID (default: claude-haiku-4-5-20251001)",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite existing triggers.yaml",
        ),
    ] = False,
) -> None:
    """Generate trigger test cases for a skill using an LLM.

    Reads SKILL.md and generates .skill-lab/tests/triggers.yaml with
    ~10-12 test cases across all 4 trigger types (explicit, implicit,
    contextual, negative).

    Requires the 'anthropic' package: pip install skill-lab[generate]
    """
    skill_path = _resolve_skill_path(skill_path)

    # Lazy import — anthropic is an optional dependency
    try:
        from skill_lab.triggers.generator import TriggerGenerator
    except ImportError:
        console.print(
            "[red]Error: The 'anthropic' package is required for test generation.[/red]\n"
            "[dim]Install it with:[/dim] pip install skill-lab[generate]"
        )
        raise typer.Exit(code=1) from None

    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[red]Error: ANTHROPIC_API_KEY environment variable is not set.[/red]\n"
            "[dim]Set it with:[/dim] export ANTHROPIC_API_KEY=sk-..."
        )
        raise typer.Exit(code=1)

    # Check for existing file (prompt unless --force)
    output_path = skill_path / TESTS_DIR / "triggers.yaml"
    if output_path.exists() and not force:
        overwrite = typer.confirm(f"Trigger tests already exist at {output_path}. Overwrite?")
        if not overwrite:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(code=0)
        force = True

    # Resolve model: --model flag > SKLAB_MODEL env var > default
    resolved_model = model or os.environ.get("SKLAB_MODEL") or None

    with _cli_error_handler():
        kwargs: dict[str, str] = {}
        if resolved_model:
            kwargs["model"] = resolved_model

        generator = TriggerGenerator(api_key=api_key, **kwargs)

        with console.status("[cyan]Generating trigger tests...[/cyan]", spinner="dots"):
            written_path = generator.generate_and_write(skill_path, force=force)

    # Print summary
    import yaml

    content = yaml.safe_load(written_path.read_text())
    test_cases = content.get("test_cases", [])
    type_counts: dict[str, int] = {}
    for tc in test_cases:
        t = tc.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    console.print(f"\n[green]Generated {len(test_cases)} trigger tests:[/green]")
    for type_name, count in sorted(type_counts.items()):
        console.print(f"  {type_name}: {count}")

    # Show token usage and cost
    if generator.last_usage:
        usage = generator.last_usage
        cost = usage.total_cost
        cost_str = f" (${cost:.4f})" if cost is not None else ""
        console.print(
            f"\n[dim]Tokens:[/dim] {usage.input_tokens:,} in + "
            f"{usage.output_tokens:,} out = {usage.total_tokens:,}{cost_str}"
        )

    console.print(f"\n[dim]Written to:[/dim] {written_path}")
    console.print("[dim]Run[/dim] sklab trigger [dim]to execute them.[/dim]")


@app.command("info")
@_with_telemetry("info")
def info(
    skill_path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the skill directory (defaults to current directory)",
        ),
    ] = None,
    json: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON (pipe-friendly)",
        ),
    ] = False,
    field: Annotated[
        str | None,
        typer.Option(
            "--field",
            "-f",
            help="Extract a single field value",
        ),
    ] = None,
) -> None:
    """Show skill metadata and token cost estimates."""
    skill_path = _resolve_skill_path(skill_path)
    skill = parse_skill(skill_path)

    if skill.metadata is None:
        console.print("[red]Error: Could not parse skill metadata.[/red]")
        raise typer.Exit(code=1)

    # Read full SKILL.md content for activation cost
    skill_md_content = (skill_path / "SKILL.md").read_text(encoding="utf-8")

    # Compute token estimates
    name = skill.metadata.name or ""
    description = skill.metadata.description or ""
    discovery_text = f"{name} {description}".strip()
    discovery_tokens = estimate_tokens(discovery_text)
    activation_tokens = estimate_tokens(skill_md_content)

    # Detect subfolders
    subfolders = []
    if skill.has_scripts:
        subfolders.append("scripts/")
    if skill.has_references:
        subfolders.append("references/")
    if skill.has_assets:
        subfolders.append("assets/")

    body_lines = len(skill.body.splitlines()) if skill.body else 0

    # Build data dict for JSON/field extraction
    raw = skill.metadata.raw
    data: dict[str, object] = {
        "name": name,
        "description": description,
        "license": raw.get("license", ""),
        "compatibility": raw.get("compatibility", ""),
        "structure": subfolders,
        "body_lines": body_lines,
        "tokens": {
            "discovery": discovery_tokens,
            "activation": activation_tokens,
        },
    }

    # --field: extract a single value
    if field is not None:
        value = data.get(field)
        if value is None:
            console.print(f"[red]Unknown field: {field}[/red]")
            raise typer.Exit(code=1)
        if isinstance(value, (dict, list)):
            print(json_module.dumps(value))
        else:
            print(value)
        return

    # --json: output everything as JSON
    if json:
        print(json_module.dumps(data, indent=2))
        return

    # Default: Rich panel
    lines: list[str] = []
    lines.append(f"[bold]Description:[/bold] {description}")
    license_val = raw.get("license", "")
    if license_val:
        lines.append(f"[bold]License:[/bold]     {license_val}")
    compat_val = raw.get("compatibility", "")
    if compat_val:
        lines.append(f"[bold]Compat:[/bold]      {compat_val}")
    lines.append("")
    if subfolders:
        lines.append(f"[bold]Structure:[/bold]   {' '.join(subfolders)}")
    lines.append(f"[bold]Body:[/bold]        {body_lines} lines")
    lines.append("")
    lines.append("[bold]Tokens (estimated):[/bold]")
    lines.append(f"  Discovery:   ~{discovery_tokens} tokens (name + description)")
    lines.append(f"  Activation:  ~{activation_tokens} tokens (full SKILL.md)")

    panel = Panel("\n".join(lines), title=f"[bold]{name}[/bold]", expand=False)
    console.print(panel)


@app.command("prompt")
@_with_telemetry("prompt")
def prompt(
    skill_paths: Annotated[
        list[Path] | None,
        typer.Argument(
            help="Paths to skill directories (defaults to current directory)",
        ),
    ] = None,
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: xml, markdown, json",
        ),
    ] = "xml",
) -> None:
    """Export skill(s) as a prompt for agent platforms."""
    from skill_lab.exporters.prompt_exporter import render_json, render_markdown, render_xml

    if format not in ("xml", "markdown", "json"):
        console.print(f"[red]Invalid format: {format}[/red]")
        console.print("[dim]Valid formats: xml, markdown, json[/dim]")
        raise typer.Exit(code=1)

    paths = skill_paths if skill_paths else [Path.cwd()]
    skills_data: list[dict[str, str]] = []

    for sp in paths:
        resolved = _resolve_skill_path(sp)
        skill = parse_skill(resolved)
        if skill.metadata is None:
            console.print(f"[red]Error: Could not parse skill metadata in {resolved}[/red]")
            raise typer.Exit(code=1)
        skills_data.append(
            {
                "name": skill.metadata.name or "",
                "description": skill.metadata.description or "",
                "location": str(resolved),
            }
        )

    if format == "xml":
        output = render_xml(skills_data)
    elif format == "markdown":
        output = render_markdown(skills_data)
    else:
        output = render_json(skills_data)

    print(output)

    # Token estimate summary to stderr (skip for JSON — keep output parseable)
    if format != "json":
        token_est = estimate_tokens(
            " ".join(f"{s['name']} {s['description']}" for s in skills_data)
        )
        print(
            f"# {len(skills_data)} skill(s), ~{token_est} discovery tokens",
            file=sys.stderr,
        )


@app.command("eval-trace", hidden=True)
@_with_telemetry("eval-trace")
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
        report_json = json_module.dumps(report.to_dict(), indent=2)
        if output:
            output.write_text(report_json)
            console.print(f"Report written to: {output}")
        else:
            console.print(report_json)
    else:
        # Use verbose=True to show all checks (trace checks are typically few)
        trace_reporter = ConsoleReporter(verbose=True)
        trace_reporter.report_trace(report)

    if not report.overall_pass:
        raise typer.Exit(code=1)


# =============================================================================
# sklab stats  (sub-app)
# =============================================================================

stats_app = typer.Typer(
    name="stats",
    help="Show personal usage statistics.",
    invoke_without_command=True,
    add_completion=False,
)
app.add_typer(stats_app)


@stats_app.callback(invoke_without_command=True)
def stats(ctx: typer.Context) -> None:
    """Show usage statistics overview."""
    init_telemetry()
    from skill_lab.core.setup import init_hooks_on_first_run

    init_hooks_on_first_run()

    if ctx.invoked_subcommand is not None:
        return

    from skill_lab.core.stats import get_overview_stats
    from skill_lab.reporters.stats_reporter import print_stats_overview

    data = get_overview_stats()
    if data is None:
        console.print("[yellow]No usage data found yet.[/yellow]")
        console.print("[dim]Run some sklab commands first, then check back here.[/dim]")
        return
    print_stats_overview(data)


def _resolve_repo_filter(here: bool) -> Path | None:
    """Return repo root Path if --here is set, else None (global)."""
    if not here:
        return None
    root = _find_repo_root(Path.cwd())
    return root if root is not None else Path.cwd()


@stats_app.command("count")
@_with_telemetry("stats-count")
def stats_count(
    here: Annotated[
        bool,
        typer.Option("--here", help="Limit to skills in the current git repo."),
    ] = False,
) -> None:
    """Show skill invocation counts for the current month."""
    from skill_lab.core.stats import get_stats_count
    from skill_lab.reporters.stats_reporter import print_stats_count

    month_label, rows = get_stats_count(repo_root=_resolve_repo_filter(here))
    print_stats_count(month_label, rows)


@stats_app.command("score")
@_with_telemetry("stats-score")
def stats_score(
    here: Annotated[
        bool,
        typer.Option("--here", help="Limit to skills in the current git repo."),
    ] = False,
) -> None:
    """Show score trend for all evaluated skills."""
    from skill_lab.core.stats import get_stats_score
    from skill_lab.reporters.stats_reporter import print_stats_score

    rows = get_stats_score(repo_root=_resolve_repo_filter(here))
    print_stats_score(rows)


@stats_app.command("tokens")
@_with_telemetry("stats-tokens")
def stats_tokens(
    here: Annotated[
        bool,
        typer.Option("--here", help="Limit to skills in the current git repo."),
    ] = False,
) -> None:
    """Show token usage per skill for the current month."""
    from skill_lab.core.stats import get_stats_tokens
    from skill_lab.reporters.stats_reporter import print_stats_tokens

    month_label, rows = get_stats_tokens(repo_root=_resolve_repo_filter(here))
    print_stats_tokens(month_label, rows)


# =============================================================================
# sklab setup
# =============================================================================


@app.command("setup")
def setup() -> None:
    """Configure hooks for automatic skill invocation tracking.

    Writes PostToolUse hooks to Claude Code (~/.claude/settings.json) and
    Cursor (~/.cursor/hooks.json) so that sklab records a row in
    ~/.sklab/usage.db every time a skill fires. Safe to run multiple times.
    """
    from skill_lab.core.setup import run_setup

    console.print("[bold]Setting up sklab skill tracking hooks...[/bold]\n")
    results = run_setup()

    for tool, status in results.items():
        if status == "configured":
            console.print(f"  [green]\u2713[/green] {tool}: hook configured")
        elif status == "already_configured":
            console.print(f"  [dim]\u2013[/dim] {tool}: already configured")
        else:
            console.print(f"  [dim]\u2013[/dim] {tool}: {status.replace('_', ' ')}")

    newly_configured = [t for t, s in results.items() if s == "configured"]
    console.print()
    if newly_configured:
        console.print(
            "[green]Done![/green] Skill invocations will be tracked automatically.\n"
            "[dim]Run [bold]sklab stats[/bold] to view your usage.[/dim]"
        )
    else:
        console.print("[dim]No changes made.[/dim]")


# =============================================================================
# sklab _track-invocation  (hidden — called by PostToolUse hooks)
# =============================================================================


def _find_skill_md(skill_name: str, cwd: str) -> Path | None:
    """Search common locations for a skill's SKILL.md. Returns path if found."""
    search_dirs = [
        Path.home() / ".claude" / "skills" / skill_name,
        Path.home() / ".cursor" / "skills" / skill_name,
    ]
    if cwd:
        search_dirs += [
            Path(cwd) / ".claude" / "skills" / skill_name,
            Path(cwd) / "skills" / skill_name,
        ]
    for skill_dir in search_dirs:
        if (skill_dir / "SKILL.md").exists():
            return skill_dir
    return None


@app.command("_track-invocation", hidden=True)
def track_invocation() -> None:
    """Record a skill invocation from a PostToolUse hook. Reads JSON from stdin."""
    from skill_lab.core.tokens import estimate_tokens

    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        data = json_module.loads(raw)
        skill_name: str = data.get("tool_input", {}).get("skill", "")
        if not skill_name:
            return
        cwd: str = data.get("cwd", "")
        skill_dir = _find_skill_md(skill_name, cwd)
        tokens: int | None = None
        skill_path_str: str | None = None
        if skill_dir is not None:
            skill_path_str = str(skill_dir)
            import contextlib

            with contextlib.suppress(Exception):
                tokens = estimate_tokens((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
        repo_root: Path | None = None
        if skill_dir is not None:
            repo_root = _find_repo_root(skill_dir)
        elif cwd:
            repo_root = _find_repo_root(Path(cwd))
        repo_hash = compute_repo_root_hash(str(repo_root) if repo_root else None)
        record_event(
            command="skill-invoke",
            duration_ms=0,
            exit_code=0,
            skill_name=skill_name,
            input_tokens=tokens,
            skill_path=skill_path_str,
            repo_root_hash=repo_hash,
        )
    except Exception:
        pass  # Never let the hook crash


# =============================================================================
# Register command modules (must be after app and helpers are defined)
# =============================================================================

import skill_lab.commands  # noqa: E402, F401, I001


# =============================================================================
# Entry point
# =============================================================================


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
