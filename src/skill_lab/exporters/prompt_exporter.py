"""Multi-format prompt export for agent platforms."""

import html
import json


def render_xml(skills: list[dict[str, str]]) -> str:
    """Render skills as XML for Claude-style agent prompts."""
    lines = ["<available_skills>"]
    for s in skills:
        lines.append("<skill>")
        lines.append(f"<name>{html.escape(s['name'])}</name>")
        lines.append(f"<description>{html.escape(s['description'])}</description>")
        lines.append(f"<location>{html.escape(s['location'])}</location>")
        lines.append("</skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)


def render_markdown(skills: list[dict[str, str]]) -> str:
    """Render skills as Markdown."""
    lines = ["## Available Skills", ""]
    for s in skills:
        lines.append(f"### {s['name']}")
        lines.append(f"**Description:** {s['description']}")
        lines.append(f"**Location:** `{s['location']}`")
        lines.append("")
    return "\n".join(lines)


def render_json(skills: list[dict[str, str]]) -> str:
    """Render skills as JSON."""
    return json.dumps({"available_skills": skills}, indent=2)
