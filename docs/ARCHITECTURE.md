# Tech Stack & Architecture

This document provides a comprehensive overview of Skill-Lab's technology stack and system architecture.

## Tech Stack

### Runtime Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| **Python** | ≥3.10 | Runtime (uses modern features like `X \| Y` union syntax) |
| **Typer** | ≥0.9.0 | CLI framework built on Click with type hints |
| **Rich** | ≥13.0.0 | Terminal formatting (tables, panels, colors) |
| **PyYAML** | ≥6.0 | YAML frontmatter parsing |

### Development Dependencies

| Package | Purpose |
|---------|---------|
| **pytest** | Test framework |
| **pytest-cov** | Test coverage reporting |
| **mypy** | Static type checking (strict mode enabled) |
| **ruff** | Fast linter (replaces flake8, isort) |

---

## Architecture Overview

### Directory Structure

```
src/skill_lab/
├── cli.py                    # Entry point - Typer CLI commands
├── __main__.py               # Allows `python -m skill_lab`
├── core/
│   ├── models.py             # Data classes (Skill, CheckResult, etc.)
│   ├── registry.py           # Check auto-discovery system
│   └── scoring.py            # Quality score calculation
├── parsers/
│   └── skill_parser.py       # SKILL.md parser (YAML + markdown)
├── checks/
│   ├── base.py               # StaticCheck abstract base class
│   └── static/               # Check implementations
│       ├── structure.py      # 5 checks
│       ├── naming.py         # 4 checks
│       ├── description.py    # 5 checks
│       └── content.py        # 6 checks
├── evaluators/
│   └── static_evaluator.py   # Orchestrates check execution
└── reporters/
    ├── console_reporter.py   # Rich terminal output
    └── json_reporter.py      # JSON output
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    USER: skill-lab evaluate ./my-skill                  │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CLI (cli.py)                                                           │
│  • Parses arguments with Typer                                          │
│  • Creates StaticEvaluator                                              │
│  • Dispatches to appropriate reporter                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  StaticEvaluator (evaluators/static_evaluator.py)                       │
│  • Imports check modules → triggers @register_check decorators          │
│  • Calls parse_skill() to get Skill object                              │
│  • Retrieves all checks from registry                                   │
│  • Executes each check.run(skill)                                       │
│  • Calculates score and builds summary                                  │
│  • Returns EvaluationReport                                             │
└─────────────────────────────────────────────────────────────────────────┘
                    │                               │
                    ▼                               ▼
┌─────────────────────────────┐   ┌───────────────────────────────────────┐
│  SkillParser                │   │  CheckRegistry                        │
│  (parsers/skill_parser.py)  │   │  (core/registry.py)                   │
│                             │   │                                       │
│  1. Read SKILL.md           │   │  Global singleton holding all         │
│  2. Extract YAML frontmatter│   │  registered check classes             │
│  3. Parse with yaml.safe_load│  │                                       │
│  4. Detect subfolders       │   │  Methods:                             │
│  5. Return Skill object     │   │  • register(check_class)              │
│                             │   │  • get_all() → list[StaticCheck]      │
└─────────────────────────────┘   │  • get_by_dimension(dim)              │
                                  └───────────────────────────────────────┘
                                                    ▲
                                                    │ @register_check
                    ┌───────────────────────────────┴────────────────────────┐
                    │                    │                    │              │
            ┌───────────────┐    ┌───────────────┐    ┌───────────────┐ ┌──────────┐
            │ structure.py  │    │  naming.py    │    │description.py │ │content.py│
            │ (5 checks)    │    │  (4 checks)   │    │ (5 checks)    │ │(6 checks)│
            └───────────────┘    └───────────────┘    └───────────────┘ └──────────┘
```

---

## Core Components

### Data Models (`core/models.py`)

#### Enumerations

```python
class Severity(str, Enum):
    ERROR = "error"      # Must fix (weight: 1.0)
    WARNING = "warning"  # Should fix (weight: 0.5)
    INFO = "info"        # Suggestion (weight: 0.25)

class EvalDimension(str, Enum):
    STRUCTURE = "structure"      # 30% weight
    NAMING = "naming"            # 20% weight
    DESCRIPTION = "description"  # 25% weight
    CONTENT = "content"          # 25% weight
```

#### Immutable Data Classes

```python
@dataclass(frozen=True)
class Skill:
    path: Path
    metadata: Optional[SkillMetadata]  # name, description, raw dict
    body: str                           # Markdown content after frontmatter
    has_scripts: bool                   # /scripts folder exists
    has_references: bool                # /references folder exists
    has_assets: bool                    # /assets folder exists
    parse_errors: tuple[str, ...]       # Errors during parsing

@dataclass(frozen=True)
class CheckResult:
    check_id: str           # e.g., "structure.skill-md-exists"
    check_name: str         # e.g., "SKILL.md Exists"
    passed: bool
    severity: Severity
    dimension: EvalDimension
    message: str
    details: Optional[dict] # Additional context
    location: Optional[str] # File path where issue found
```

---

### Check Registration Pattern

The check registration system uses Python's decorator and module import mechanism for auto-discovery.

#### 1. Global Registry (Singleton)

```python
# core/registry.py
class CheckRegistry:
    _checks: dict[str, type[StaticCheck]] = {}

    def register(self, check_class) -> check_class:
        self._checks[check_class.check_id] = check_class
        return check_class  # Returns class for decorator use

registry = CheckRegistry()  # Global singleton

def register_check(check_class):
    return registry.register(check_class)
```

#### 2. Check Definition (with decorator)

```python
# checks/static/structure.py
@register_check  # ← Adds to global registry when module loads
class SkillMdExistsCheck(StaticCheck):
    check_id = "structure.skill-md-exists"
    check_name = "SKILL.md Exists"
    severity = Severity.ERROR
    dimension = EvalDimension.STRUCTURE

    def run(self, skill: Skill) -> CheckResult:
        if (skill.path / "SKILL.md").exists():
            return self._pass("SKILL.md found")
        return self._fail("SKILL.md not found")
```

#### 3. Registration Trigger (import side effect)

```python
# evaluators/static_evaluator.py
from skill_lab.checks.static import content, description, naming, structure

# This import executes the module code, which runs @register_check decorators
# Now registry.get_all() returns all 20 check classes
```

#### Why This Pattern?

- **Zero manual wiring** - add decorator, checks are auto-discovered
- **Easy testing** - `registry.clear()` for isolation
- **Selective execution** - pass `check_ids` to run a subset

---

### Scoring Algorithm (`core/scoring.py`)

#### Step 1: Per-Dimension Score

For each dimension, calculate: `(passed_weight / total_weight) * 100`

Weights by severity:
- ERROR = 1.0
- WARNING = 0.5
- INFO = 0.25

#### Step 2: Weighted Average

Final score = Σ(dimension_score × dimension_weight)

```python
DIMENSION_WEIGHTS = {
    STRUCTURE: 0.30,     # 30%
    NAMING: 0.20,        # 20%
    DESCRIPTION: 0.25,   # 25%
    CONTENT: 0.25,       # 25%
}
```

#### Example Calculation

```
Structure: 5 checks, all pass       → 100 × 0.30 = 30.0
Naming: 4 checks, 1 ERROR fails     →  75 × 0.20 = 15.0
Description: 5 checks, all pass     → 100 × 0.25 = 25.0
Content: 6 checks, 1 WARNING fails  →  90 × 0.25 = 22.5
──────────────────────────────────────────────────────
Final Score: 92.5
```

---

### Parser (`parsers/skill_parser.py`)

The parser handles:

1. **Frontmatter extraction** via regex: `^---\n(.*?)^---\n`
2. **YAML parsing** with `yaml.safe_load()`
3. **Metadata extraction** - pulls `name` and `description` fields
4. **Subfolder detection** - checks for `/scripts`, `/references`, `/assets`
5. **Graceful error handling** - collects errors in `parse_errors` tuple instead of throwing

---

### CLI Commands (`cli.py`)

Built with **Typer** which provides:
- Automatic `--help` generation
- Type validation from annotations
- Path validation (`exists=True`, `dir_okay=True`)

```bash
# Main evaluation command
skill-lab evaluate ./my-skill [--format console|json] [--output file.json] [--verbose]

# Quick validation (exit 0 or 1)
skill-lab validate ./my-skill

# List available checks
skill-lab list-checks [--dimension structure|naming|description|content]
```

---

### Reporters

#### ConsoleReporter

Uses Rich library for terminal output:
- Panel with skill name/path
- Color-coded score (green ≥80, yellow ≥60, red <60)
- Table of results with severity icons
- Dimension summary

#### JsonReporter

Structured output for programmatic use:
- Full `EvaluationReport` serialized via `to_dict()` methods
- Machine-readable for CI/CD integration

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Immutable models** (`frozen=True`) | Ensures check results can't be accidentally modified |
| **Error collection vs throwing** | Parser collects errors in tuple, evaluation continues |
| **Decorator-based registration** | No central file listing all checks needed |
| **Weighted scoring** | Different severities and dimensions have different impact |
| **Strict typing** | mypy strict mode enforced in `pyproject.toml` |

---

## Adding a New Check

1. Create a class extending `StaticCheck` in the appropriate `checks/static/` module
2. Define class attributes: `check_id`, `check_name`, `description`, `severity`, `dimension`
3. Implement `run(skill: Skill) -> CheckResult` using `self._pass()` or `self._fail()`
4. Add the `@register_check` decorator - no other wiring needed

```python
@register_check
class MyNewCheck(StaticCheck):
    check_id: ClassVar[str] = "dimension.my-check"
    check_name: ClassVar[str] = "My Check Name"
    description: ClassVar[str] = "What this check verifies"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        if some_condition:
            return self._pass("Check passed")
        return self._fail("Check failed", details={"reason": "..."})
```
