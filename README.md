# Skill Lab

[![PyPI version](https://badge.fury.io/py/skill-lab.svg?v=0.2.0)](https://badge.fury.io/py/skill-lab)
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

## Quick Start

```bash
# Evaluate a skill (path defaults to current directory)
sklab evaluate ./my-skill
sklab evaluate                    # Uses current directory

# Quick validation (pass/fail)
sklab validate ./my-skill
sklab validate                    # Uses current directory

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

### Trigger Testing

Test whether skills activate correctly with real LLM execution:

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

> **Note:** Codex CLI support is coming in v0.3.0.

**Test Definition** (`tests/triggers.yaml`):

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

## License

MIT
