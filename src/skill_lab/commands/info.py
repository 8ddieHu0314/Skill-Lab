"""Info, prompt, and eval-trace commands."""

import json as json_module
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from skill_lab.cli import (
    OutputFormat,
    _resolve_skill_path,
    _with_telemetry,
    app,
    console,
)
from skill_lab.core.tokens import estimate_tokens
from skill_lab.evaluators.trace_evaluator import TraceEvaluator
from skill_lab.parsers.skill_parser import parse_skill
from skill_lab.reporters.console_reporter import ConsoleReporter


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
