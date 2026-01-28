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
│   ├── models.py             # Data classes (Skill, CheckResult, TriggerResult, etc.)
│   ├── registry.py           # Check auto-discovery system
│   └── scoring.py            # Quality score calculation
├── parsers/
│   └── skill_parser.py       # SKILL.md parser (YAML + markdown)
├── checks/
│   ├── base.py               # StaticCheck abstract base class
│   └── static/               # Check implementations
│       ├── structure.py      # 5 checks
│       ├── naming.py         # 5 checks
│       ├── description.py    # 5 checks
│       └── content.py        # 6 checks
├── evaluators/
│   └── static_evaluator.py   # Orchestrates static check execution
├── triggers/                 # Trigger testing (Phase 2)
│   ├── test_loader.py        # Load test cases from YAML
│   ├── trace_analyzer.py     # Analyze execution traces
│   └── trigger_evaluator.py  # Orchestrates trigger tests
├── runtimes/                 # Runtime adapters (Phase 2)
│   ├── base.py               # RuntimeAdapter abstract base class
│   ├── codex_runtime.py      # OpenAI Codex CLI adapter
│   └── claude_runtime.py     # Claude Code CLI adapter
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
│                             │   │  • get_by_dimension(dim)              │
│                             │   │  • get_spec_required()                │
└─────────────────────────────┘   │  • get_quality_suggestions()          │
                                  └───────────────────────────────────────┘
                                                    ▲
                                                    │ @register_check
                    ┌───────────────────────────────┴────────────────────────┐
                    │                    │                    │              │
            ┌───────────────┐    ┌───────────────┐    ┌───────────────┐ ┌──────────┐
            │ structure.py  │    │  naming.py    │    │description.py │ │content.py│
            │ (5 checks)    │    │  (5 checks)   │    │ (5 checks)    │ │(6 checks)│
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

class TriggerType(str, Enum):  # Phase 2
    EXPLICIT = "explicit"        # Skill named with $ prefix
    IMPLICIT = "implicit"        # Scenario without naming skill
    CONTEXTUAL = "contextual"    # Noisy real-world prompt
    NEGATIVE = "negative"        # Should NOT trigger
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
# Now registry.get_all() returns all 21 check classes
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
Naming: 5 checks, 1 ERROR fails     →  80 × 0.20 = 16.0
Description: 5 checks, all pass     → 100 × 0.25 = 25.0
Content: 6 checks, 1 WARNING fails  →  90 × 0.25 = 22.5
──────────────────────────────────────────────────────
Final Score: 93.5
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
skill-lab evaluate ./my-skill [--format console|json] [--output file.json] [--verbose] [--spec-only]

# Quick validation (exit 0 or 1)
skill-lab validate ./my-skill [--spec-only]

# List available checks
skill-lab list-checks [--dimension structure|naming|description|content] [--spec-only] [--suggestions-only]

# Trigger testing (Phase 2)
skill-lab test-triggers ./my-skill [--runtime codex|claude] [--type explicit|implicit|contextual|negative] [--format console|json]
```

**Spec Filtering:**
- `--spec-only` / `-s`: Only run checks required by the Agent Skills spec (8 checks)
- `--suggestions-only`: List only quality suggestion checks (13 checks)

**Trigger Testing:**
- `--runtime` / `-r`: Select runtime adapter (codex, claude, or auto-detect)
- `--type` / `-t`: Filter by trigger type (explicit, implicit, contextual, negative)

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

## Trigger Testing (Phase 2)

Trigger testing verifies that skills activate correctly for different prompt types.

### Trigger Types

| Type | Description | Example |
|------|-------------|---------|
| **EXPLICIT** | Skill named directly with $ prefix | `$create-react-app for a todo list` |
| **IMPLICIT** | Describes exact scenario without naming skill | `I need to scaffold a new React application` |
| **CONTEXTUAL** | Realistic noisy prompt with domain context | `Building a dashboard, can you set up React?` |
| **NEGATIVE** | Should NOT trigger (catches false positives) | `How do I fix this useState hook?` |

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Trigger Test Flow                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Load test cases from YAML                                           │
│     tests/scenarios.yaml → Given/When/Then DSL                          │
│     tests/triggers.yaml  → Simple flat format                           │
│                              │                                          │
│  2. Execute prompts via Runtime Adapter                                 │
│     RuntimeAdapter (Codex CLI or Claude CLI)                            │
│     → Skill metadata injected into context                              │
│     → Prompt sent to LLM                                                │
│     → Execution trace captured as JSONL                                 │
│                              │                                          │
│  3. Analyze trace for skill invocation                                  │
│     TraceAnalyzer → Was skill X invoked? Commands run? Loops detected?  │
│                              │                                          │
│  4. Report trigger success/failure                                      │
│     TriggerReport → pass rate by type, failures list                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Models

```python
class TriggerType(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"
    CONTEXTUAL = "contextual"
    NEGATIVE = "negative"

@dataclass(frozen=True)
class TraceEvent:
    type: str                    # e.g., "item.started", "item.completed"
    item_type: Optional[str]     # e.g., "command_execution"
    command: Optional[str]       # The command that was run
    output: Optional[str]        # Command output
    timestamp: Optional[str]
    raw: dict                    # Original event for debugging

@dataclass(frozen=True)
class TriggerTestCase:
    id: str
    name: str
    skill_name: str
    prompt: str
    trigger_type: TriggerType
    expected: TriggerExpectation
    runtime: Optional[str]

@dataclass(frozen=True)
class TriggerResult:
    test_id: str
    test_name: str
    trigger_type: TriggerType
    passed: bool
    skill_triggered: bool
    expected_trigger: bool
    message: str
    trace_path: Optional[Path]
    events_count: int
```

### Runtime Adapters

Runtime adapters execute skills and capture traces:

```python
class RuntimeAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def execute(self, prompt: str, skill_path: Path, trace_path: Path) -> int: ...

    @abstractmethod
    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]: ...
```

**CodexRuntime**: Executes via `codex exec --json --full-auto`
**ClaudeRuntime**: Executes via `claude --print --output-format stream-json`

### Test Definition Formats

**Given/When/Then DSL** (`tests/scenarios.yaml`):
```yaml
skill: my-skill
scenarios:
  - name: "Direct invocation"
    given:
      - skill: my-skill
      - runtime: codex
    when:
      - prompt: "$my-skill do something"
      - trigger_type: explicit
    then:
      - skill_triggered: true
      - exit_code: 0
```

**Simple Format** (`tests/triggers.yaml`):
```yaml
skill: my-skill
test_cases:
  - id: explicit-1
    type: explicit
    prompt: "$my-skill do something"
    expected: trigger
```

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
3. Set `spec_required = True` if the check enforces the Agent Skills spec (default is `False`)
4. Implement `run(skill: Skill) -> CheckResult` using `self._pass()` or `self._fail()`
5. Add the `@register_check` decorator - no other wiring needed

```python
@register_check
class MyNewCheck(StaticCheck):
    check_id: ClassVar[str] = "dimension.my-check"
    check_name: ClassVar[str] = "My Check Name"
    description: ClassVar[str] = "What this check verifies"
    severity: ClassVar[Severity] = Severity.WARNING
    dimension: ClassVar[EvalDimension] = EvalDimension.CONTENT
    spec_required: ClassVar[bool] = False  # True if required by Agent Skills spec

    def run(self, skill: Skill) -> CheckResult:
        if some_condition:
            return self._pass("Check passed")
        return self._fail("Check failed", details={"reason": "..."})
```

**Check Categories:**
- **Spec-required checks** (8): Must pass to be valid per the Agent Skills spec. Use `spec_required = True` and `Severity.ERROR`.
- **Quality suggestions** (13): Best practices that improve skill quality. Use `spec_required = False` (default) with `Severity.WARNING` or `Severity.INFO`.
