# Skill Lab

[![PyPI version](https://badge.fury.io/py/skill-lab.svg?v=0.4.0)](https://badge.fury.io/py/skill-lab)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python CLI tool for evaluating agent skills through static analysis, trigger testing, and trace analysis.

## Features

- **SKILL.md Parsing**: Parse YAML frontmatter and markdown body from skill definitions
- **19 Static Checks**: Comprehensive checks across 4 dimensions
  - Structure: File existence, folder organization, frontmatter validation, standard fields
  - Naming: Format, directory matching
  - Description: Required, non-empty, max length
  - Content: Examples, line budget, reference depth
- **Trigger Testing**: Test skill activation with 4 trigger types (explicit, implicit, contextual, negative)
- **Trigger Generation**: LLM-powered test case generation via Anthropic API
- **Skill Inspector**: `sklab info` shows metadata and token cost estimates
- **Prompt Export**: `sklab prompt` exports skills as XML, Markdown, or JSON for agent platforms
- **Quality Scoring**: Weighted 0-100 score based on check results
- **Multiple Output Formats**: Console (rich formatting) and JSON

## Installation

```bash
# From PyPI
pip install skill-lab

# From source
pip install -e .

# With development dependencies
pip install -e ".[dev]"
```

## Setup

### API Key (required for `sklab generate`)

`sklab generate` uses the Anthropic API to generate trigger test cases. Set your API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Get your key at [console.anthropic.com](https://console.anthropic.com).

### Model Configuration (optional)

The default model is `claude-haiku-4-5-20251001`. Override it per-command or globally:

```bash
# Per-command
sklab generate ./my-skill --model claude-sonnet-4-5-20250929

# Global default via environment variable
export SKLAB_MODEL=claude-sonnet-4-5-20250929
```

## Quick Start

After installing, run `sklab` to scan your repo for skills and see an initial evaluation:

```bash
sklab                             # First run: scans repo + shows Getting Started guide
```

```bash
# Evaluate a skill (path defaults to current directory)
sklab evaluate ./my-skill
sklab evaluate                    # Uses current directory
sklab evaluate --all              # Evaluate every skill in the current directory
sklab evaluate --repo             # Evaluate every skill from the git repo root

# Quick validation (pass/fail)
sklab validate ./my-skill

# Inspect skill metadata and token costs
sklab info ./my-skill
sklab info ./my-skill --json      # Machine-readable output

# Export skills as a prompt for agent platforms
sklab prompt ./skill-a ./skill-b  # XML (default)
sklab prompt -f markdown          # Markdown format
sklab prompt -f json              # JSON format

# Generate trigger test cases (requires ANTHROPIC_API_KEY)
sklab generate ./my-skill

# Run trigger tests
sklab trigger ./my-skill

# List available checks
sklab list-checks
```

## Usage

### Evaluate a Skill

```bash
# Console output (default)
sklab evaluate ./my-skill

# JSON output
sklab evaluate ./my-skill --format json

# Save to file
sklab evaluate ./my-skill --output report.json

# Verbose (show all checks, not just failures)
sklab evaluate ./my-skill --verbose

# Spec-only (skip quality suggestions)
sklab evaluate ./my-skill --spec-only

# Bulk evaluation
sklab evaluate --all              # All skills under current directory
sklab evaluate --repo             # All skills from git repo root
```

### Quick Validation

```bash
# Returns exit code 0 if valid, 1 if invalid
sklab validate ./my-skill
```

### List Available Checks

```bash
# List all checks
sklab list-checks

# Filter by dimension
sklab list-checks --dimension structure

# Show only spec-required checks
sklab list-checks --spec-only
```

### Inspect Skill Metadata

View skill metadata and token cost estimates:

```bash
# Rich-formatted panel (default)
sklab info ./my-skill

# JSON output (pipe-friendly)
sklab info ./my-skill --json

# Extract a single field
sklab info ./my-skill --field name
sklab info ./my-skill --field tokens
```

Token estimates show **discovery cost** (name + description, what agents see when choosing skills) and **activation cost** (full SKILL.md, loaded when the skill is invoked).

### Export as Prompt

Export one or more skills into a prompt format for agent platforms:

```bash
# XML format (default, recommended for Claude)
sklab prompt ./skill-a ./skill-b

# Markdown format
sklab prompt ./my-skill -f markdown

# JSON format
sklab prompt ./my-skill -f json
```

Output goes to stdout for easy piping. A token estimate summary is printed to stderr.

### Generate Trigger Tests

Auto-generate trigger test cases from a SKILL.md using an LLM:

```bash
# Generate tests (writes to .skill-lab/tests/triggers.yaml)
sklab generate ./my-skill

# Use a specific model
sklab generate ./my-skill --model claude-sonnet-4-5-20250929

# Overwrite existing tests
sklab generate ./my-skill --force
```

Generates ~13 test cases across 4 trigger types:
- **explicit** (3): Direct `$skill-name` invocation
- **implicit** (3): Describes the need without naming the skill
- **contextual** (3): Realistic prompts with project context
- **negative** (4): Adjacent requests that should NOT trigger

Token usage and cost are displayed after each run.

### Trigger Testing

Run the generated (or hand-written) trigger tests against a real LLM:

```bash
# Run trigger tests (path defaults to current directory)
sklab trigger ./my-skill
sklab trigger                     # Uses current directory

# Filter by trigger type
sklab trigger --type explicit
sklab trigger --type negative
```

**Prerequisites:** Trigger testing requires:
- **Claude CLI**: Install via `npm install -g @anthropic-ai/claude-code`

**Test Definition** (`.skill-lab/tests/triggers.yaml`):

```yaml
skill: my-skill
test_cases:
  - id: explicit-1
    name: "Direct invocation to do something"
    type: explicit
    prompt: "$my-skill do something"
    expected: trigger
  - id: negative-1
    name: "Unrelated question (should not trigger)"
    type: negative
    prompt: "unrelated question"
    expected: no_trigger
```

## Output Format (JSON)

```json
{
  "skill_path": "/path/to/skill",
  "skill_name": "my-skill",
  "timestamp": "2026-01-25T14:30:00Z",
  "duration_ms": 45.3,
  "quality_score": 87.5,
  "overall_pass": true,
  "checks_run": 19,
  "checks_passed": 17,
  "checks_failed": 2,
  "results": [...],
  "summary": {
    "by_severity": {...},
    "by_dimension": {...}
  }
}
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=skill_lab

# Type checking
mypy src/

# Linting
ruff check src/

# Format code
ruff format src/
```

## Telemetry

sklab collects anonymous usage data to help improve your experience and the tool. On first interactive run a notice is printed. **No skill content, file paths, or flag values are ever collected.**

What is collected: command names, flags used, duration, exit codes, OS, Python version, sklab version, skill names, skill versions, evaluation scores, token counts (input + output), session ID, CI environment, and error types (class name only — no messages or content).

To opt out, set an environment variable before running any `sklab` command:

```bash
export SKLAB_NO_ANALYTICS=1   # sklab-specific
export DO_NOT_TRACK=1          # standard cross-tool opt-out
```

See [docs/PRIVACY.md](docs/PRIVACY.md) for the full privacy policy.

## License

MIT
