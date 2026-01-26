# Agent Skills Evaluation Framework

A Python CLI tool for evaluating agent skills through static analysis and quality checks.

## Features

- **SKILL.md Parsing**: Parse YAML frontmatter and markdown body from skill definitions
- **20 Static Checks**: Comprehensive checks across 4 dimensions
  - Structure: File existence, folder organization
  - Naming: Format, reserved words, conventions
  - Description: Length, voice, trigger information
  - Content: Examples, line budget, cross-platform compatibility
- **Quality Scoring**: Weighted 0-100 score based on check results
- **Multiple Output Formats**: Console (rich formatting) and JSON

## Installation

```bash
# From source
pip install -e .

# With development dependencies
pip install -e ".[dev]"
```

## Usage

### Evaluate a Skill

```bash
# Console output (default)
agent-skills-eval evaluate ./my-skill

# JSON output
agent-skills-eval evaluate ./my-skill --format json

# Save to file
agent-skills-eval evaluate ./my-skill --output report.json

# Verbose (show all checks, not just failures)
agent-skills-eval evaluate ./my-skill --verbose
```

### Quick Validation

```bash
# Returns exit code 0 if valid, 1 if invalid
agent-skills-eval validate ./my-skill
```

### List Available Checks

```bash
# List all checks
agent-skills-eval list-checks

# Filter by dimension
agent-skills-eval list-checks --dimension structure
```

## Check Categories

### Structure Checks
| Check ID | Severity | Description |
|----------|----------|-------------|
| `structure.skill-md-exists` | ERROR | SKILL.md file exists |
| `structure.valid-frontmatter` | ERROR | YAML frontmatter is parseable |
| `structure.scripts-valid` | WARNING | /scripts contains valid files |
| `structure.references-valid` | WARNING | /references contains valid files |
| `structure.no-unexpected-files` | INFO | No unexpected files in root |

### Naming Checks
| Check ID | Severity | Description |
|----------|----------|-------------|
| `naming.required` | ERROR | Name field is present |
| `naming.format` | ERROR | Lowercase, hyphens only, max 64 chars |
| `naming.no-reserved` | ERROR | No reserved words (anthropic, claude) |
| `naming.gerund-convention` | WARNING | Uses gerund form (e.g., "creating-") |

### Description Checks
| Check ID | Severity | Description |
|----------|----------|-------------|
| `description.required` | ERROR | Description field is present |
| `description.not-empty` | ERROR | Description is not empty |
| `description.max-length` | ERROR | Max 1024 characters |
| `description.third-person` | WARNING | Uses third-person voice |
| `description.includes-triggers` | WARNING | Describes when to use |

### Content Checks
| Check ID | Severity | Description |
|----------|----------|-------------|
| `content.body-not-empty` | ERROR | Body has content (min 50 chars) |
| `content.line-budget` | WARNING | Under 500 lines |
| `content.has-examples` | INFO | Contains code examples |
| `content.no-windows-paths` | WARNING | No backslash paths |
| `content.no-time-sensitive` | WARNING | No hardcoded dates |
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
  "checks_run": 20,
  "checks_passed": 18,
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
pytest tests/ --cov=agent_skills_eval

# Type checking
mypy src/

# Linting
ruff check src/
```

## Project Structure

```
agent-skills-eval/
├── src/agent_skills_eval/
│   ├── cli.py                    # CLI interface
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
│   │   └── static_evaluator.py   # Orchestration
│   └── reporters/
│       ├── json_reporter.py
│       └── console_reporter.py
├── tests/
└── examples/
```

## License

MIT
