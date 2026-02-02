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
│   ├── registry.py           # Check auto-discovery system (extends generic Registry[T])
│   ├── scoring.py            # Quality score calculation and shared metrics
│   ├── utils.py              # Shared utilities (generic Registry[T], serialize_value)
│   └── exceptions.py         # Custom exception hierarchy (SkillLabError, ParseError, etc.)
├── parsers/
│   ├── skill_parser.py       # SKILL.md parser (YAML + markdown)
│   └── trace_parser.py       # JSONL trace parser
├── checks/
│   ├── base.py               # StaticCheck abstract base class
│   └── static/               # Check implementations
│       ├── structure.py      # 4 checks
│       ├── frontmatter.py    # 3 checks
│       ├── naming.py         # 3 checks
│       ├── description.py    # 4 checks
│       └── content.py        # 4 checks
├── evaluators/
│   ├── static_evaluator.py   # Orchestrates static check execution
│   └── trace_evaluator.py    # Orchestrates trace check execution
├── tracechecks/              # Trace analysis (Phase 3)
│   ├── __init__.py
│   ├── registry.py           # TraceCheckRegistry with @register_trace_handler
│   ├── trace_check_loader.py # Load check definitions from YAML
│   └── handlers/             # Trace check handler implementations
│       ├── base.py           # TraceCheckHandler ABC
│       ├── command_presence.py
│       ├── file_creation.py
│       ├── event_sequence.py
│       ├── loop_detection.py
│       └── efficiency.py
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
│                    USER: sklab evaluate ./my-skill                  │
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
            │ structure.py  │ │frontmatter.py│ │  naming.py  │ │description.py│ │content.py│
            │ (4 checks)    │ │  (3 checks)  │ │ (3 checks)  │ │  (4 checks)  │ │(4 checks)│
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
    EXECUTION = "execution"      # 0% (evaluated separately via trace checks)

class TriggerType(str, Enum):  # Phase 2
    EXPLICIT = "explicit"        # Skill named with $ prefix
    IMPLICIT = "implicit"        # Scenario without naming skill
    CONTEXTUAL = "contextual"    # Noisy real-world prompt
    NEGATIVE = "negative"        # Should NOT trigger
```

#### Immutable Data Classes

All models use Python 3.10+ union syntax (`T | None`) instead of `Optional[T]`:

```python
@dataclass(frozen=True)
class Skill:
    path: Path
    metadata: SkillMetadata | None  # name, description, raw dict
    body: str                        # Markdown content after frontmatter
    has_scripts: bool                # /scripts folder exists
    has_references: bool             # /references folder exists
    has_assets: bool                 # /assets folder exists
    parse_errors: tuple[str, ...]    # Errors during parsing

@dataclass(frozen=True)
class CheckResult:
    check_id: str            # e.g., "structure.skill-md-exists"
    check_name: str          # e.g., "SKILL.md Exists"
    passed: bool
    severity: Severity
    dimension: EvalDimension
    message: str
    details: dict | None     # Additional context
    location: str | None     # File path where issue found
```

---

### Check Registration Pattern

The check registration system uses Python's decorator and module import mechanism for auto-discovery. Both static checks and trace handlers share a generic `Registry[T]` base class.

#### 1. Generic Registry Base Class

```python
# core/utils.py
class Registry(Generic[T]):
    """Generic registry for auto-discovery patterns."""

    def __init__(self, id_extractor: Callable[[type[T]], str]) -> None:
        self._items: dict[str, type[T]] = {}
        self._id_extractor = id_extractor

    def register(self, item_class: type[T]) -> type[T]:
        item_id = self._id_extractor(item_class)
        self._items[item_id] = item_class
        return item_class

    def get(self, item_id: str) -> type[T] | None:
        return self._items.get(item_id)

    def get_all(self) -> list[type[T]]:
        return list(self._items.values())
```

#### 2. Specialized Check Registry

```python
# core/registry.py
class CheckRegistry(Registry["StaticCheck"]):
    """Registry for static checks with dimension filtering."""

    def __init__(self) -> None:
        super().__init__(id_extractor=lambda cls: cls.check_id)

    def get_by_dimension(self, dimension: str) -> list[type[StaticCheck]]: ...
    def get_spec_required(self) -> list[type[StaticCheck]]: ...
    def get_quality_suggestions(self) -> list[type[StaticCheck]]: ...

registry = CheckRegistry()  # Global singleton

def register_check(check_class):
    return registry.register(check_class)
```

#### 3. Check Definition (with decorator)

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

#### 4. Base Class Helper Methods

The `StaticCheck` base class provides helper methods to reduce code duplication:

```python
# checks/base.py
class StaticCheck(ABC):
    def _skill_md_location(self, skill: Skill) -> str:
        """Get the standard location string for SKILL.md."""
        return str(skill.path / "SKILL.md")

    def _require_metadata(self, skill: Skill, context: str = "perform this check") -> CheckResult | None:
        """Check that skill has metadata, returning a failure result if not."""
        if skill.metadata is None:
            return self._fail(
                f"No frontmatter found, cannot {context}",
                location=self._skill_md_location(skill),
            )
        return None

    def _pass(self, message: str, **kwargs) -> CheckResult: ...
    def _fail(self, message: str, **kwargs) -> CheckResult: ...
```

Usage in checks:
```python
def run(self, skill: Skill) -> CheckResult:
    # Early return if no metadata
    if result := self._require_metadata(skill, "check name field"):
        return result
    assert skill.metadata is not None  # Type narrowing for mypy
    # ... check logic using skill.metadata
```

#### 5. Registration Trigger (import side effect)

```python
# evaluators/static_evaluator.py
from skill_lab.checks.static import content, description, frontmatter, naming, structure

# This import executes the module code, which runs @register_check decorators
# Now registry.get_all() returns all 18 check classes
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

#### Shared Metric Utilities

All evaluators (static, trace, trigger) use shared utilities for consistent metric calculation:

```python
# core/scoring.py
@dataclass
class EvaluationMetrics:
    total: int
    passed: int
    failed: int
    pass_rate: float

def calculate_metrics(results: list[T]) -> EvaluationMetrics:
    """Calculate pass/fail metrics from any list of results with a 'passed' attribute."""
    ...

def build_summary_by_attribute(
    results: list[T],
    attribute: str,
    value_extractor: Callable[[Any], str] | None = None,
) -> dict[str, dict[str, int]]:
    """Build summary statistics grouped by an attribute (e.g., dimension, check_type)."""
    ...
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
sklab evaluate ./my-skill [--format console|json] [--output file.json] [--verbose] [--spec-only]

# Quick validation (exit 0 or 1)
sklab validate ./my-skill [--spec-only]

# List available checks
sklab list-checks [--dimension structure|naming|description|content] [--spec-only] [--suggestions-only]

# Trigger testing (Phase 2)
sklab trigger ./my-skill [--runtime codex|claude] [--type explicit|implicit|contextual|negative] [--format console|json]

# Trace evaluation (Phase 3)
sklab eval-trace ./my-skill --trace ./execution.jsonl [--format console|json] [--output file.json]
```

**Spec Filtering:**
- `--spec-only` / `-s`: Only run checks required by the Agent Skills spec (10 checks)
- `--suggestions-only`: List only quality suggestion checks (8 checks)

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
- **Verbose hints**: When checks are hidden in non-verbose mode, displays "(N passing checks hidden, run with --verbose to see all)"

#### JsonReporter

Structured output for programmatic use:
- Full `EvaluationReport` serialized via `to_dict()` methods
- Machine-readable for CI/CD integration
- **Schema versioning**: Includes `"schema_version": "1.0"` field for API consumers to track compatibility

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
    type: str                 # e.g., "item.started", "item.completed"
    item_type: str | None     # e.g., "command_execution"
    command: str | None       # The command that was run
    output: str | None        # Command output
    timestamp: str | None
    raw: dict                 # Original event for debugging

@dataclass(frozen=True)
class TriggerTestCase:
    id: str
    name: str
    skill_name: str
    prompt: str
    trigger_type: TriggerType
    expected: TriggerExpectation
    runtime: str | None

@dataclass(frozen=True)
class TriggerResult:
    test_id: str
    test_name: str
    trigger_type: TriggerType
    passed: bool
    skill_triggered: bool
    expected_trigger: bool
    message: str
    trace_path: Path | None
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
| **Generic Registry[T]** | Eliminates code duplication between CheckRegistry and TraceCheckRegistry |
| **Base class helpers** | `_require_metadata()`, `_skill_md_location()`, `_require_field()` reduce repetitive null-checks |
| **Shared metric utilities** | `calculate_metrics()` ensures consistent pass/fail calculation across all evaluators |
| **Custom exception hierarchy** | `SkillLabError` base with `context` and `suggestion` fields for actionable error messages |
| **T \| None over Optional[T]** | Python 3.10+ union syntax for cleaner, more readable type annotations |

---

### Custom Exception Hierarchy (`core/exceptions.py`)

All custom exceptions extend `SkillLabError` which provides structured error handling:

```python
class SkillLabError(Exception):
    """Base exception for sklab with context and suggestions."""
    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,  # Additional error context
        suggestion: str | None = None,           # Actionable guidance
    ) -> None: ...

class ParseError(SkillLabError):
    """Errors during parsing (YAML, traces, etc.)."""

class CheckExecutionError(SkillLabError):
    """Errors during check execution."""

class TraceParseError(ParseError):
    """Errors specific to trace file parsing."""

class TestDefinitionError(SkillLabError):
    """Errors in test definition files."""

class RuntimeError(SkillLabError):
    """Errors from runtime adapters."""
```

Usage:
```python
raise ParseError(
    "Invalid YAML frontmatter",
    context={"line": 5, "file": "SKILL.md"},
    suggestion="Ensure frontmatter starts and ends with '---'"
)
```

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
- **Spec-required checks** (10): Must pass to be valid per the Agent Skills spec. Use `spec_required = True` and `Severity.ERROR`.
- **Quality suggestions** (8): Best practices that improve skill quality. Use `spec_required = False` (default) with `Severity.WARNING` or `Severity.INFO`.

---

## Trace Analysis (Phase 3)

Trace analysis validates execution traces against YAML-defined checks. This enables skill authors to define custom checks for command presence, file creation, event sequences, and loop detection.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Trace Evaluation Flow                                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Load check definitions from YAML                                    │
│     tests/trace_checks.yaml → TraceCheckDefinition objects              │
│                              │                                          │
│  2. Parse trace file                                                    │
│     execution.jsonl → TraceEvent list → TraceAnalyzer                   │
│                              │                                          │
│  3. Run each check via handler                                          │
│     TraceCheckRegistry.get(type) → Handler.run() → TraceCheckResult     │
│                              │                                          │
│  4. Build report                                                        │
│     TraceReport → pass rate, summary by type                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Check Types

| Type | Description | YAML Fields |
|------|-------------|-------------|
| **command_presence** | Did specific command run? | `pattern` |
| **file_creation** | Was expected file created? | `path` |
| **event_sequence** | Commands in correct order? | `sequence` |
| **loop_detection** | Detect thrashing/excessive retries | `max_retries` |
| **efficiency** | Token usage, command count limits | `max_commands` |

### Trace Check Definition (YAML)

```yaml
# tests/trace_checks.yaml
checks:
  - id: npm-install-ran
    type: command_presence
    pattern: "npm install"

  - id: package-json-created
    type: file_creation
    path: "package.json"

  - id: correct-sequence
    type: event_sequence
    sequence: ["npm init", "npm install", "npm run build"]

  - id: no-excessive-retries
    type: loop_detection
    max_retries: 3

  - id: command-count-limit
    type: efficiency
    max_commands: 20
```

### Data Models

```python
@dataclass(frozen=True)
class TraceCheckDefinition:
    """A trace check defined in YAML."""
    id: str
    type: str  # command_presence, file_creation, event_sequence, loop_detection, efficiency
    description: str | None = None
    pattern: str | None = None          # for command_presence
    path: str | None = None             # for file_creation
    sequence: tuple[str, ...] = ()      # for event_sequence
    max_retries: int = 3                # for loop_detection
    max_commands: int | None = None     # for efficiency

@dataclass(frozen=True)
class TraceCheckResult:
    """Result of a single trace check execution."""
    check_id: str
    check_type: str
    passed: bool
    message: str
    details: dict | None = None

@dataclass
class TraceReport:
    """Complete trace evaluation report."""
    trace_path: str
    project_dir: str
    timestamp: str
    duration_ms: float
    checks_run: int
    checks_passed: int
    checks_failed: int
    overall_pass: bool
    pass_rate: float
    results: list[TraceCheckResult]
    summary: dict
```

### Handler Registration Pattern

Similar to static checks, trace handlers use a decorator-based registration system. The `TraceCheckRegistry` also extends the generic `Registry[T]` base class.

```python
from skill_lab.tracechecks.registry import register_trace_handler
from skill_lab.tracechecks.handlers.base import TraceCheckHandler

@register_trace_handler("command_presence")
class CommandPresenceHandler(TraceCheckHandler):
    def run(self, check, analyzer, project_dir) -> TraceCheckResult:
        # Use _require_field() helper for parameter validation
        pattern = self._require_field(check, "pattern")
        if isinstance(pattern, TraceCheckResult):
            return pattern  # Missing field, return error result

        if analyzer.command_was_run(pattern):
            return self._pass(check, f"Command matching '{pattern}' was executed")
        return self._fail(check, f"No command matching '{pattern}' found")
```

The `TraceCheckHandler` base class provides:
- `_pass(check, message, details)` - Create passing result
- `_fail(check, message, details)` - Create failing result
- `_require_field(check, field_name)` - Validate required YAML fields, returns error result if missing
