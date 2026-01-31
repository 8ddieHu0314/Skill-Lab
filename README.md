# Skill Lab

[![PyPI version](https://badge.fury.io/py/skill-lab.svg)](https://badge.fury.io/py/skill-lab)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/8ddieHu0314/Skill-Lab/actions/workflows/test.yml/badge.svg)](https://github.com/8ddieHu0314/Skill-Lab/actions/workflows/test.yml)

A Python CLI tool for evaluating agent skills through static analysis and quality checks.

## Features

- **SKILL.md Parsing**: Parse YAML frontmatter and markdown body from skill definitions
- **18 Static Checks**: Comprehensive checks across 4 dimensions
  - Structure: File existence, folder organization, frontmatter validation
  - Naming: Format, directory matching
  - Description: Length, trigger information
  - Content: Examples, line budget, reference depth
- **Quality Scoring**: Weighted 0-100 score based on check results
- **Multiple Output Formats**: Console (rich formatting) and JSON
- **Trace Evaluation**: Analyze execution traces against defined checks
- **Trigger Testing**: Verify skill activation with different prompt types

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
# Evaluate a skill
sklab evaluate ./my-skill

# Quick validation (pass/fail)
sklab validate ./my-skill

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

### Test Triggers

```bash
# Run trigger tests
sklab test-triggers ./my-skill

# Filter by trigger type
sklab test-triggers ./my-skill --type explicit
```

### Evaluate Traces

```bash
# Evaluate an execution trace
sklab eval-trace ./my-skill --trace ./trace.jsonl
```

## Check Categories

### Structure Checks
| Check ID | Severity | Description |
|----------|----------|-------------|
| `structure.skill-md-exists` | ERROR | SKILL.md file exists |
| `structure.valid-frontmatter` | ERROR | YAML frontmatter is parseable |
| `frontmatter.compatibility-length` | ERROR | Compatibility under 500 chars |
| `frontmatter.metadata-format` | ERROR | Metadata is string-to-string map |
| `structure.scripts-valid` | WARNING | /scripts contains valid files |
| `structure.references-valid` | WARNING | /references contains valid files |

### Naming Checks
| Check ID | Severity | Description |
|----------|----------|-------------|
| `naming.required` | ERROR | Name field is present |
| `naming.format` | ERROR | Lowercase, hyphens only, max 64 chars |
| `naming.matches-directory` | ERROR | Name matches parent directory |

### Description Checks
| Check ID | Severity | Description |
|----------|----------|-------------|
| `description.required` | ERROR | Description field is present |
| `description.not-empty` | ERROR | Description is not empty |
| `description.max-length` | ERROR | Max 1024 characters |
| `description.includes-triggers` | INFO | Describes when to use |

### Content Checks
| Check ID | Severity | Description |
|----------|----------|-------------|
| `content.body-not-empty` | WARNING | Body has content (min 50 chars) |
| `content.line-budget` | WARNING | Under 500 lines |
| `content.has-examples` | INFO | Contains code examples |
| `content.reference-depth` | WARNING | References max 1 level deep |

## Output Format (JSON)

```json
{
  "skill_path": "/path/to/skill",
  "skill_name": "my-skill",
  "timestamp": "2026-01-25T14:30:00Z",
  "duration_ms": 45.3,
  "quality_score": 87.5,
  "overall_pass": true,
  "checks_run": 18,
  "checks_passed": 19,
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

## Project Structure

```
sklab/
├── src/skill_lab/
│   ├── cli.py                    # CLI interface (Typer)
│   ├── core/
│   │   ├── models.py             # Data models
│   │   ├── registry.py           # Check registration
│   │   └── scoring.py            # Quality scoring
│   ├── parsers/
│   │   └── skill_parser.py       # SKILL.md parsing
│   ├── checks/
│   │   ├── base.py               # Base check class
│   │   └── static/               # Static checks
│   ├── evaluators/
│   │   ├── static_evaluator.py   # Static analysis
│   │   └── trace_evaluator.py    # Trace evaluation
│   ├── triggers/
│   │   └── trigger_evaluator.py  # Trigger testing
│   └── reporters/
│       ├── json_reporter.py
│       └── console_reporter.py
├── tests/
├── docs/
└── examples/
```

## Related

- [Agent Skills Specification](https://agentskills.io/specification) - The specification this tool validates against
- [SkillsMP](https://skillsmp.com) - Marketplace for agent skills

## License

MIT
