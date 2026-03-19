"""Security scan command."""

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from skill_lab.cli import (
    _cli_error_handler,
    _discover_skills,
    _resolve_skill_path,
    _with_telemetry,
    app,
    console,
)
from skill_lab.core.telemetry import push_telemetry_extra


def _run_bulk_scan(roots: list[Path], verbose: bool = False) -> None:
    """Discover and security-scan all skills under the given root directories."""
    from skill_lab.checks.static.security import SecurityScanCheck
    from skill_lab.parsers.skill_parser import parse_skill

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
        try:
            skill = parse_skill(sp)
        except Exception as e:
            console.print(f"[red]Error parsing {sp.name}: {e}[/red]")
            any_blocked = True
            continue

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
            if verbose:
                console.print(f"[bold]{skill_name}[/bold] ({rel_path})")
                for f in findings:
                    console.print(f"  [yellow]~[/yellow] {f.get('problem', '')} — {f.get('text', '')}")
                console.print()
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

    has_issues = any_blocked or any("SUS" in status_str for _, _, status_str in summary_rows)
    if has_issues:
        console.print("[dim]Run [bold]sklab scan <path>[/bold] on any skill above for full details.[/dim]")

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
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Show findings for SUS skills in addition to BLOCK (bulk mode only)",
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
        _run_bulk_scan([Path.cwd()], verbose=verbose)
        return

    skill_path = _resolve_skill_path(skill_path)
    push_telemetry_extra(skill_name=skill_path.name)

    with _cli_error_handler():
        from skill_lab.parsers.skill_parser import parse_skill

        skill = parse_skill(skill_path)

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
