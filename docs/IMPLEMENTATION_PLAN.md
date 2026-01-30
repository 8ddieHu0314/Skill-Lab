# Skill-Lab Unified Implementation Plan

This document defines the implementation roadmap for Skill-Lab, a unified agent skill evaluation and benchmarking platform.

---

## Vision

Build **infrastructure for skill testing at scale** - tooling that enables automated quality evaluation, test execution, and regression detection for Agent Skills.

### The Gap We're Filling

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  OpenAI Blog (Pedagogical)          │  Skill-Lab (Infrastructural)          │
├─────────────────────────────────────┼───────────────────────────────────────┤
│  "Test with 4 trigger types"        │  DSL + automated runner + storage     │
│  "Parse JSONL traces"               │  Trace parser + check framework       │
│  "Use rubrics"                      │  LLM-as-judge pipeline                │
│  "Track regressions"                │  History storage + CI/CD gates        │
│  (silent on marketplace)            │  Quality badges + trend data          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Two-Sided Value Proposition

**For Skill Authors (Supply Side):**
- DSL for defining test scenarios (given/when/then patterns)
- Automated test execution and result tracking
- Visualization of improvement over versions
- Easy publication to skill directories with quality badges

**For Skill Consumers (Demand Side):**
- Quality metrics for every published skill
- Trend data showing quality over time
- Category benchmarks for comparison
- Confidence in skill reliability

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SKILL-LAB ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  TEST DEFINITION LAYER                                               │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │   │
│  │  │ scenarios/  │  │ triggers/   │  │ traces/     │  │ rubrics/    │  │   │
│  │  │ given-when- │  │ explicit    │  │ commands    │  │ criteria    │  │   │
│  │  │ then DSL    │  │ implicit    │  │ files       │  │ weights     │  │   │
│  │  │             │  │ contextual  │  │ sequences   │  │             │  │   │
│  │  │             │  │ negative    │  │             │  │             │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  EXECUTION LAYER                                                     │   │
│  │  ┌─────────────────────────┐    ┌─────────────────────────┐          │   │
│  │  │  Codex Runtime Adapter  │    │  Claude Runtime Adapter │          │   │
│  │  │  codex exec --json      │    │  MCP / Claude Code      │          │   │
│  │  └─────────────────────────┘    └─────────────────────────┘          │   │
│  │                    │                        │                        │   │
│  │                    └────────┬───────────────┘                        │   │
│  │                             ▼                                        │   │
│  │              ┌─────────────────────────────┐                         │   │
│  │              │  Normalized TraceEvent Log  │                         │   │
│  │              └─────────────────────────────┘                         │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  EVALUATION LAYER                                                    │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │   │
│  │  │ Static      │  │ Trigger     │  │ Trace       │  │ Rubric      │  │   │
│  │  │ Evaluator   │  │ Evaluator   │  │ Evaluator   │  │ Evaluator   │  │   │
│  │  │ (23 checks) │  │ (4 types)   │  │ (determin.) │  │ (LLM judge) │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │   │
│  │                    │                        │                │       │   │
│  │                    └────────────┬───────────┴────────────────┘       │   │
│  │                                 ▼                                    │   │
│  │                   ┌─────────────────────────────┐                    │   │
│  │                   │  Composite Quality Score    │                    │   │
│  │                   │  + Breakdown + Tier         │                    │   │
│  │                   └─────────────────────────────┘                    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  OUTPUT LAYER                                                        │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │   │
│  │  │ Console     │  │ JSON        │  │ Badge       │  │ Marketplace │  │   │
│  │  │ Reporter    │  │ Reporter    │  │ Generator   │  │ Publisher   │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                   │   │
│  │  │ History     │  │ Trend       │  │ CI/CD       │                   │   │
│  │  │ Storage     │  │ Visualizer  │  │ Gate        │                   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quality Scoring System

### Composite Quality Score

The final score combines all evaluation dimensions:

```json
{
  "overall_score": 87,
  "tier": "silver",
  "breakdown": {
    "static_analysis": 92,
    "trigger_accuracy": 85,
    "execution_reliability": 88,
    "rubric_score": 82
  },
  "trend": "+5 from v1.2.0"
}
```

### Quality Tiers with Badges

```
┌────────────────────────────────────────────────────────────┐
│  Quality Tier System                                       │
├────────────────────────────────────────────────────────────┤
│  Gold   (90-100)  - Production ready, well-tested          │
│  Silver (75-89)   - Good quality, minor issues             │
│  Bronze (60-74)   - Functional, needs improvement          │
│  Unrated (<60)    - Not recommended for production         │
├────────────────────────────────────────────────────────────┤
│  Badge URL: sklab.dev/badge/{skill-name}.svg           │
│  Example:   ![Quality](sklab.dev/badge/my-skill.svg)   │
└────────────────────────────────────────────────────────────┘
```

### Score Weights (Configurable)

```yaml
# Default weights for composite score
scoring:
  static_analysis: 0.25      # SKILL.md quality
  trigger_accuracy: 0.30     # 4-type trigger testing
  execution_reliability: 0.25 # Trace-based checks
  rubric_score: 0.20         # LLM-as-judge
```

---

## Phased Roadmap

| Phase | Focus | Status | Deliverables |
|-------|-------|--------|--------------|
| **Phase 1** | Static Analysis (MVP) | **DONE** | SKILL.md parsing, 23 static checks, JSON output, CLI |
| **Phase 2** | Trigger Testing | **DONE** | Given/When/Then DSL, runtime adapters, 4-type trigger tests, CLI |
| **Phase 3** | Trace Analysis | **DONE** | JSONL parsing, command/file/sequence checks, efficiency metrics |
| **Phase 4** | Rubric Grading | Planned | LLM-as-judge pipeline, structured output |
| **Phase 5** | Ecosystem Integration | Planned | Quality badges, marketplace publishing, CI/CD gates, benchmarks |

---

## Design Decisions (Confirmed)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Execution Model** | Orchestrate directly + consume traces | Skill-Lab sends prompts to LLM, captures and analyzes traces |
| **Phase Priority** | Trigger Testing first | Most impactful for skill quality validation |
| **Storage** | File-based (YAML/JSON) | Version-controllable, no dependencies, simple |
| **LLM Providers** | Both (configurable) | Support OpenAI (Codex) and Anthropic (Claude) |
| **Runtimes** | Codex CLI + Claude/MCP | Support both agent runtimes for cross-platform coverage |
| **Trace Format** | Normalize to common TraceEvent | Both Codex JSONL and Claude traces converted to unified model |

---

# Phase 1: Static Analysis (MVP) - COMPLETE

## What Was Built

A Python CLI tool that:
1. Parses SKILL.md files and validates folder structure
2. Runs 23 static checks across 4 dimensions
3. Outputs JSON/Console evaluation reports
4. Provides a weighted quality score (0-100)

## Current Architecture

```
src/skill_lab/
├── cli.py                    # Typer CLI (evaluate, validate, list-checks)
├── core/
│   ├── models.py             # Skill, CheckResult, EvaluationReport
│   ├── registry.py           # Check auto-discovery via @register_check
│   └── scoring.py            # Weighted quality score calculation
├── parsers/
│   └── skill_parser.py       # SKILL.md + folder structure parsing
├── checks/
│   ├── base.py               # StaticCheck base class
│   └── static/
│       ├── structure.py      # 5 checks
│       ├── frontmatter.py    # 3 checks (30% weight combined with structure)
│       ├── naming.py         # 4 checks (20% weight)
│       ├── description.py    # 5 checks (25% weight)
│       └── content.py        # 6 checks (25% weight)
├── evaluators/
│   └── static_evaluator.py   # Orchestrates check execution
└── reporters/
    ├── console_reporter.py   # Rich terminal output
    └── json_reporter.py      # Structured JSON output
```

## Deliverables (Complete)

- [x] SKILL.md parser with YAML frontmatter extraction
- [x] 23 static checks across 4 dimensions
- [x] CheckRegistry with @register_check decorator
- [x] Weighted quality score calculation
- [x] CLI: `evaluate`, `validate`, `list-checks` commands
- [x] Console reporter (Rich)
- [x] JSON reporter

---

# Phase 2: Trigger Testing - COMPLETE

## Goal

Test whether skills activate correctly by sending real prompts to LLMs with skill metadata loaded, then analyzing execution traces for skill invocations.

## Trigger Test Types (from OpenAI methodology)

| Type | Description | Example |
|------|-------------|---------|
| **Explicit** | Skill named directly with $ prefix | `$create-react-app for a todo list` |
| **Implicit** | Describes exact scenario without naming skill | `I need to scaffold a new React application` |
| **Contextual** | Realistic noisy prompt with domain context | `Building a dashboard, can you set up React with routing?` |
| **Negative** | Should NOT trigger (catches false positives) | `How do I fix this useState hook?` |

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  Trigger Test Flow                                                 │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  1. Load test cases from YAML                                      │
│     triggers.yaml → explicit, implicit, contextual, negative       │
│                              │                                     │
│  2. Send prompts to LLM with skill loaded                          │
│     Runtime Adapter (Codex CLI or Claude/MCP)                      │
│     → Skill metadata injected into system prompt                   │
│     → Prompt sent to LLM                                           │
│     → Execution trace captured                                     │
│                              │                                     │
│  3. Analyze trace for skill invocation                             │
│     TraceAnalyzer → Was skill X invoked? (yes/no)                  │
│                              │                                     │
│  4. Report trigger success/failure                                 │
│     TriggerReport → pass rate by type, failures list               │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## New Components

```
src/skill_lab/
├── core/
│   └── models.py              # Add TriggerTestCase, TriggerResult, TriggerReport
├── triggers/
│   ├── __init__.py
│   ├── test_loader.py         # Load test cases from YAML (includes DSL parsing)
│   ├── trigger_evaluator.py   # Orchestrate trigger tests
│   └── trace_analyzer.py      # Detect skill invocations in traces
├── runtimes/
│   ├── __init__.py
│   ├── base.py                # Abstract RuntimeAdapter ABC
│   ├── codex_runtime.py       # OpenAI Codex CLI integration
│   └── claude_runtime.py      # Claude Code / MCP integration
└── config/
    └── runtime_config.py      # Runtime selection, API keys
```

## Test Scenario DSL (Given/When/Then)

The DSL provides an expressive way to define test scenarios:

```yaml
# my-skill/tests/scenarios.yaml
skill: create-react-app
version: "1.0.0"

scenarios:
  # Explicit trigger test
  - name: "Direct skill invocation"
    given:
      - skill: create-react-app
      - runtime: codex
    when:
      - prompt: "$create-react-app for a todo list"
      - trigger_type: explicit
    then:
      - skill_triggered: true
      - exit_code: 0

  # Implicit trigger test
  - name: "Scaffold React app with TypeScript"
    given:
      - skill: create-react-app
      - runtime: codex
    when:
      - prompt: "I need to scaffold a new React application with TypeScript"
      - trigger_type: implicit
    then:
      - skill_triggered: true
      - commands_include: ["npx create-react-app", "npm install"]
      - files_created: ["package.json", "tsconfig.json", "src/App.tsx"]
      - no_loops: true

  # Contextual trigger test
  - name: "Realistic noisy prompt"
    given:
      - skill: create-react-app
      - runtime: claude
    when:
      - prompt: "I'm building a dashboard for my company. Can you set up a new React project with routing and a component library?"
      - trigger_type: contextual
    then:
      - skill_triggered: true
      - files_created: ["package.json"]

  # Negative control test
  - name: "Should not trigger for component fix"
    given:
      - skill: create-react-app
      - runtime: codex
    when:
      - prompt: "How do I fix this useState hook in my React component?"
      - trigger_type: negative
    then:
      - skill_triggered: false

  # Negative control - wrong framework
  - name: "Should not trigger for Vue"
    given:
      - skill: create-react-app
      - runtime: codex
    when:
      - prompt: "Create a Vue.js application for me"
      - trigger_type: negative
    then:
      - skill_triggered: false
```

## Simple Test Format (Alternative)

For simpler cases, a flat format is also supported:

```yaml
# my-skill/tests/triggers.yaml
skill: create-react-app

test_cases:
  - id: explicit-1
    type: explicit
    prompt: "$create-react-app for a todo list"
    expected: trigger

  - id: implicit-1
    type: implicit
    prompt: "I need to scaffold a new React application with TypeScript"
    expected: trigger

  - id: negative-1
    type: negative
    prompt: "How do I fix this useState hook?"
    expected: no_trigger
```

## Runtime Configuration

```yaml
# sklab.yaml (project config)
runtime:
  provider: codex  # or 'claude'

  codex:
    model: gpt-4

  claude:
    model: claude-sonnet-4-20250514
```

---

## Runtime Adapter Implementation

### Key Design Principle

**Everything is deterministic and debuggable.** If a check fails, you can open the JSONL file and see exactly what happened. Every command execution appears as an `item.*` event, in order. That makes regressions straightforward to explain and fix.

### Codex Runtime Adapter (Reference Implementation)

Based on OpenAI's evaluation pattern:

```python
# src/skill_lab/runtimes/codex_runtime.py
import subprocess
import json
from pathlib import Path
from typing import Iterator
from .base import RuntimeAdapter, TraceEvent

class CodexRuntime(RuntimeAdapter):
    """Execute skills via Codex CLI and capture JSONL traces."""

    def execute(self, prompt: str, skill_path: Path, trace_path: Path) -> int:
        """
        Run Codex with the given prompt, capturing structured events.

        Args:
            prompt: The user prompt to send
            skill_path: Path to the skill directory
            trace_path: Where to write the JSONL trace

        Returns:
            Exit code from Codex
        """
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [
                "codex",
                "exec",
                "--json",       # REQUIRED: emit structured events
                "--full-auto",  # Allow file system changes
                prompt,
            ],
            capture_output=True,
            text=True,
            cwd=skill_path,
        )

        # stdout is JSONL when --json is enabled
        trace_path.write_text(result.stdout)

        return result.returncode

    def parse_trace(self, trace_path: Path) -> Iterator[TraceEvent]:
        """Parse JSONL trace into normalized TraceEvent objects."""
        content = trace_path.read_text()
        for line in content.strip().split("\n"):
            if not line:
                continue
            raw = json.loads(line)
            yield self._normalize_event(raw)

    def _normalize_event(self, raw: dict) -> TraceEvent:
        """Convert Codex event to normalized TraceEvent."""
        return TraceEvent(
            type=raw.get("type"),
            item_type=raw.get("item", {}).get("type"),
            command=raw.get("item", {}).get("command"),
            output=raw.get("item", {}).get("output"),
            timestamp=raw.get("timestamp"),
            raw=raw,  # Preserve original for debugging
        )
```

### JSONL Event Types (Codex)

Codex emits these event types that we parse:

| Event Type | Description | Use Case |
|------------|-------------|----------|
| `item.started` | Command/action began | Detect skill invocation |
| `item.completed` | Command/action finished | Check command output |
| `turn.started` | Agent turn began | Track conversation flow |
| `turn.completed` | Agent turn finished | Token usage metrics |

### Deterministic Check Patterns

```python
# src/skill_lab/triggers/trace_analyzer.py
from typing import List
from pathlib import Path
from ..core.models import TraceEvent

class TraceAnalyzer:
    """Analyze traces for deterministic checks."""

    def __init__(self, events: List[TraceEvent]):
        self.events = events

    def skill_was_triggered(self, skill_name: str) -> bool:
        """Check if a specific skill was invoked."""
        return any(
            e.type in ("item.started", "item.completed") and
            e.item_type == "skill_invocation" and
            skill_name in (e.command or "")
            for e in self.events
        )

    def command_was_run(self, pattern: str) -> bool:
        """Check if a command matching pattern was executed."""
        return any(
            e.type in ("item.started", "item.completed") and
            e.item_type == "command_execution" and
            isinstance(e.command, str) and
            pattern in e.command
            for e in self.events
        )

    def file_was_created(self, filepath: str, project_dir: Path) -> bool:
        """Check if a file exists after execution."""
        return (project_dir / filepath).exists()

    def get_command_sequence(self) -> List[str]:
        """Extract ordered list of commands run."""
        return [
            e.command for e in self.events
            if e.type == "item.completed" and
            e.item_type == "command_execution" and
            e.command
        ]

    def detect_loops(self, max_repeats: int = 3) -> bool:
        """Detect if the same command was repeated too many times."""
        commands = self.get_command_sequence()
        from collections import Counter
        counts = Counter(commands)
        return any(count > max_repeats for count in counts.values())
```

### Claude Runtime Adapter (Parallel Implementation)

```python
# src/skill_lab/runtimes/claude_runtime.py
import subprocess
import json
from pathlib import Path
from typing import Iterator
from .base import RuntimeAdapter, TraceEvent

class ClaudeRuntime(RuntimeAdapter):
    """Execute skills via Claude Code and capture traces."""

    def execute(self, prompt: str, skill_path: Path, trace_path: Path) -> int:
        """
        Run Claude Code with the given prompt.

        Note: Claude Code trace format differs from Codex.
        We normalize to common TraceEvent format.
        """
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        # Claude Code execution (adjust flags as needed)
        result = subprocess.run(
            [
                "claude",
                "--print",      # Output mode
                "--output-format", "json",
                "-p", prompt,
            ],
            capture_output=True,
            text=True,
            cwd=skill_path,
        )

        trace_path.write_text(result.stdout)
        return result.returncode

    def _normalize_event(self, raw: dict) -> TraceEvent:
        """Convert Claude event to normalized TraceEvent."""
        # Map Claude's format to our common format
        # (Exact mapping depends on Claude Code's output structure)
        return TraceEvent(
            type=self._map_event_type(raw),
            item_type=raw.get("type"),
            command=raw.get("tool_input", {}).get("command"),
            output=raw.get("result"),
            timestamp=raw.get("timestamp"),
            raw=raw,
        )
```

### Normalized TraceEvent Model

```python
# src/skill_lab/core/models.py
from dataclasses import dataclass
from typing import Optional, Any

@dataclass(frozen=True)
class TraceEvent:
    """Normalized event from any runtime (Codex or Claude)."""
    type: str                    # e.g., "item.started", "item.completed"
    item_type: Optional[str]     # e.g., "command_execution", "skill_invocation"
    command: Optional[str]       # The command that was run
    output: Optional[str]        # Command output/result
    timestamp: Optional[str]     # When it occurred
    raw: dict                    # Original event for debugging
```

### Example: Full Trigger Test Execution

```python
# Example usage in TriggerEvaluator
def run_trigger_test(scenario: Scenario, runtime: RuntimeAdapter) -> TriggerResult:
    """Execute a single trigger test scenario."""

    # 1. Execute the prompt
    trace_path = Path(f"./traces/{scenario.id}.jsonl")
    exit_code = runtime.execute(
        prompt=scenario.when.prompt,
        skill_path=scenario.given.skill_path,
        trace_path=trace_path,
    )

    # 2. Parse the trace
    events = list(runtime.parse_trace(trace_path))
    analyzer = TraceAnalyzer(events)

    # 3. Run deterministic checks
    skill_triggered = analyzer.skill_was_triggered(scenario.given.skill)

    # 4. Compare to expected
    expected_trigger = scenario.then.skill_triggered
    passed = skill_triggered == expected_trigger

    return TriggerResult(
        scenario_id=scenario.id,
        passed=passed,
        skill_triggered=skill_triggered,
        expected=expected_trigger,
        trace_path=trace_path,  # For debugging if failed
        events_count=len(events),
    )
```

## CLI Commands

```bash
# Run trigger tests with default runtime
sklab test-triggers ./my-skill

# Specify runtime
sklab test-triggers ./my-skill --runtime codex
sklab test-triggers ./my-skill --runtime claude

# Run specific test type only
sklab test-triggers ./my-skill --type explicit
sklab test-triggers ./my-skill --type negative
```

## Deliverables

- [x] `TriggerTestCase`, `TriggerResult`, `TriggerReport` data models
- [x] YAML test case loader with validation
- [x] `RuntimeAdapter` abstract base class
- [x] Codex CLI runtime adapter (`codex exec --json`)
- [x] Claude/MCP runtime adapter
- [x] Trace analyzer (detect skill invocations from traces)
- [x] `TriggerEvaluator` orchestrator class
- [x] CLI command: `sklab test-triggers`
- [x] Trigger metrics in evaluation report

---

# Phase 3: Trace Analysis - COMPLETE

## Goal

Parse JSONL execution logs to validate process/outcome goals through deterministic checks.

> **Note:** Phase 2 introduces `TraceAnalyzer` for basic trigger detection. Phase 3 extends this with configurable, YAML-driven checks that skill authors can customize per skill.

## What Was Built

A YAML-driven trace check system that:
1. Loads check definitions from `tests/trace_checks.yaml`
2. Parses JSONL trace files into normalized TraceEvent objects
3. Runs checks via registered handlers (command_presence, file_creation, event_sequence, loop_detection, efficiency)
4. Produces TraceReport with pass/fail results and summary

## Architecture

```
src/skill_lab/
├── tracechecks/
│   ├── __init__.py
│   ├── registry.py             # TraceCheckRegistry with @register_trace_handler
│   ├── trace_check_loader.py   # Parse tests/trace_checks.yaml
│   └── handlers/
│       ├── base.py             # TraceCheckHandler ABC
│       ├── command_presence.py # Check if pattern found in commands
│       ├── file_creation.py    # Check if file exists at path
│       ├── event_sequence.py   # Check commands in correct order
│       ├── loop_detection.py   # Detect excessive command repetition
│       └── efficiency.py       # Check token/command count limits
├── parsers/
│   └── trace_parser.py         # Standalone JSONL parser
└── evaluators/
    └── trace_evaluator.py      # Orchestrate trace check execution
```

## Check Types

| Check | Description |
|-------|-------------|
| **Command Presence** | Did specific command run? (e.g., `npm install`) |
| **File Creation** | Was expected file created? (e.g., `package.json`) |
| **Event Sequence** | Commands in correct order? |
| **Loop Detection** | Detect thrashing/excessive retries |
| **Efficiency** | Token usage, command count metrics |

## New Components

```
src/skill_lab/
├── core/
│   └── models.py              # Add ExecutionTrace (TraceEvent defined in Phase 2)
├── parsers/
│   └── trace_parser.py        # Parse JSONL from Codex/Claude
├── checks/
│   └── execution/             # New check dimension
│       ├── command_presence.py
│       ├── file_creation.py
│       ├── event_sequence.py
│       └── loop_detection.py
└── evaluators/
    └── trace_evaluator.py     # Orchestrate trace-based checks
```

## Trace Check Definition (YAML)

```yaml
# my-skill/tests/trace_checks.yaml
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
```

## CLI Commands

```bash
sklab eval-trace ./my-skill --trace ./execution.jsonl
```

## Deliverables

- [x] `TraceCheckDefinition`, `TraceCheckResult`, `TraceReport` models
- [x] JSONL trace parser with format normalization
- [x] `TraceCheckRegistry` with `@register_trace_handler` decorator
- [x] Command presence check handler
- [x] File creation verification check handler
- [x] Event sequence validation check handler
- [x] Loop/thrashing detection check handler
- [x] Efficiency (command count) check handler
- [x] `TraceEvaluator` orchestrator class
- [x] CLI command: `sklab eval-trace`
- [x] Console reporter for trace reports
- [x] Test fixtures and unit tests

---

# Phase 4: Rubric-Based Grading

## Goal

Add LLM-powered qualitative evaluation for style and outcome goals that can't be checked deterministically.

## New Components

```
src/skill_lab/
├── core/
│   └── models.py              # Add Rubric, RubricCriterion, RubricResult
├── rubrics/
│   ├── __init__.py
│   ├── rubric_loader.py       # Load rubric definitions
│   └── rubric_evaluator.py    # LLM-powered grading
└── llm/
    ├── __init__.py
    ├── base.py                # LLM provider abstraction
    └── providers/
        ├── openai.py
        └── anthropic.py
```

## Rubric Definition (YAML)

```yaml
# my-skill/tests/rubric.yaml
rubric:
  - criterion: code_quality
    weight: 0.3
    description: "Code follows best practices and is well-structured"

  - criterion: documentation
    weight: 0.2
    description: "README and comments are clear and helpful"

  - criterion: error_handling
    weight: 0.25
    description: "Errors are handled gracefully with helpful messages"

  - criterion: conventions
    weight: 0.25
    description: "Output matches expected structure and naming conventions"
```

## CLI Commands

```bash
sklab eval-rubric ./my-skill --artifacts ./output/
```

## Deliverables

- [ ] `Rubric`, `RubricCriterion`, `RubricResult` models
- [ ] LLM provider abstraction (OpenAI + Anthropic)
- [ ] Rubric YAML loader
- [ ] `RubricEvaluator` with structured output
- [ ] CLI command: `sklab eval-rubric`

---

# Phase 5: Ecosystem Integration

## Goal

Enable marketplace publishing, quality badges, CI/CD gates, category benchmarks, and public quality history.

## New Components

```
src/skill_lab/
├── ecosystem/
│   ├── __init__.py
│   ├── badges.py              # SVG badge generator
│   ├── publisher.py           # Marketplace API client
│   └── leaderboard.py         # Category rankings
├── benchmarks/
│   ├── __init__.py
│   ├── dataset.py             # Benchmark dataset management
│   ├── runner.py              # Batch evaluation
│   └── comparator.py          # Version diff/comparison
├── storage/
│   ├── __init__.py
│   └── file_store.py          # YAML/JSON history storage
└── cicd/
    ├── __init__.py
    └── gates.py               # Quality gate logic
```

## Quality Badges

Generate embeddable SVG badges:

```bash
# Generate badge
sklab badge ./my-skill --output badge.svg

# Badge URL (if hosted)
https://sklab.dev/badge/my-skill.svg
```

Badge displays: `Skill-Lab | Silver 87`

## Marketplace Publishing

Push quality metrics to skill directories:

```bash
# Publish to marketplace
sklab publish ./my-skill --marketplace skillsmp.com

# What this does:
# 1. Runs full evaluation (static + triggers + traces + rubric)
# 2. Generates quality report
# 3. Pushes score + badge to marketplace API
# 4. Updates public quality metrics
```

## CI/CD Quality Gates

Enforce quality standards in pipelines:

```yaml
# .github/workflows/skill-quality.yml
name: Skill Quality Gate

on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Skill-Lab
        run: pip install skill-lab

      - name: Run Quality Gate
        run: |
          sklab evaluate ./my-skill \
            --min-score 80 \
            --fail-on-regression \
            --output report.json

      - name: Upload Report
        uses: actions/upload-artifact@v4
        with:
          name: quality-report
          path: report.json
```

## Category Benchmarks

Compare skills within categories:

```yaml
# sklab-benchmarks/react-scaffolding/benchmark.yaml
category: react-scaffolding
description: "Skills that scaffold React applications"

required_capabilities:
  - creates_package_json
  - installs_dependencies
  - supports_typescript

test_scenarios:
  - prompt: "Create a React app with TypeScript"
    expected_files: ["package.json", "tsconfig.json"]

  - prompt: "Scaffold React with routing"
    expected_commands: ["npm install react-router-dom"]

leaderboard:
  - skill: create-react-app-pro    score: 94  tier: gold
  - skill: react-starter           score: 87  tier: silver
  - skill: quick-react             score: 72  tier: bronze
```

```bash
# Run benchmark comparison
sklab benchmark ./my-skill --category react-scaffolding

# Output:
# Your skill: 85 (Silver)
# Category average: 78
# Rank: 2 of 15 skills
```

## Public Quality History

Optional transparency for skill consumers:

```
https://sklab.dev/skills/create-react-app/history

┌─────────────────────────────────────────────────────────────┐
│  create-react-app - Quality History                         │
├─────────────────────────────────────────────────────────────┤
│  v1.3.0  ████████████████████░░░░  87  (+5)  2026-01-27     │
│  v1.2.0  ███████████████░░░░░░░░░  82  (+3)  2026-01-20     │
│  v1.1.0  ████████████████░░░░░░░░  79  (-2)  2026-01-15     │
│  v1.0.0  ██████████████████░░░░░░  81       2026-01-10      │
└─────────────────────────────────────────────────────────────┘
```

## History Format (YAML)

```yaml
# .sklab/history/my-skill.yaml
skill: my-skill
category: react-scaffolding
evaluations:
  - timestamp: "2026-01-27T14:30:00Z"
    version: "1.3.0"
    overall_score: 87
    tier: silver
    breakdown:
      static_analysis: 92
      trigger_accuracy: 85
      execution_reliability: 88
      rubric_score: 82
    tests_run: 24
    tests_passed: 22

  - timestamp: "2026-01-20T10:00:00Z"
    version: "1.2.0"
    overall_score: 82
    tier: silver
    # ...
```

## CLI Commands

```bash
# History and comparison
sklab history ./my-skill
sklab compare ./my-skill --from v1.2.0 --to v1.3.0

# Benchmarks
sklab benchmark ./my-skill --category react-scaffolding
sklab leaderboard --category react-scaffolding

# Publishing
sklab publish ./my-skill --marketplace skillsmp.com
sklab badge ./my-skill --output badge.svg

# CI/CD
sklab evaluate ./my-skill --min-score 80 --fail-on-regression
```

## Deliverables

- [ ] SVG badge generator with tier colors
- [ ] Marketplace publisher API client
- [ ] Category benchmark runner
- [ ] Leaderboard generation
- [ ] Evaluation history storage (YAML)
- [ ] Version comparison/diff reporting
- [ ] CI/CD quality gate logic
- [ ] GitHub Actions workflow template
- [ ] Public history visualization (optional hosted service)

---

## Verification Plan

### Phase 2: Trigger Testing

```bash
# Unit tests
pytest tests/test_triggers.py -v
pytest tests/test_scenario_dsl.py -v
pytest tests/test_runtimes.py -v

# Integration test with mock runtime
pytest tests/test_trigger_integration.py -v

# Manual testing
sklab test-triggers ./examples/sample-skill --runtime codex
```

**End-to-End Test Flow:**
1. Create skill with `scenarios.yaml` using Given/When/Then DSL
2. Run `sklab test-triggers ./my-skill --runtime codex`
3. Verify trigger pass rates by type (explicit/implicit/contextual/negative)
4. Add a failing negative test case
5. Verify it's detected as a false positive

### Phase 3: Trace Analysis

```bash
# Unit tests
pytest tests/test_trace_parser.py -v
pytest tests/test_execution_checks.py -v

# Manual testing with real trace
sklab eval-trace ./my-skill --trace ./execution.jsonl
```

### Phase 4: Rubric Grading

```bash
# Unit tests
pytest tests/test_rubric_evaluator.py -v
pytest tests/test_llm_providers.py -v

# Manual testing
sklab eval-rubric ./my-skill --artifacts ./output/
```

### Phase 5: Ecosystem Integration

```bash
# Unit tests
pytest tests/test_badges.py -v
pytest tests/test_publisher.py -v
pytest tests/test_benchmarks.py -v

# Manual testing
sklab badge ./my-skill --output badge.svg
sklab history ./my-skill
sklab benchmark ./my-skill --category react-scaffolding

# CI/CD gate testing
sklab evaluate ./my-skill --min-score 80 --fail-on-regression
```

### Full Pipeline Test

```bash
# Run complete evaluation
sklab evaluate ./my-skill --full

# Expected output:
# ┌─────────────────────────────────────────┐
# │  my-skill - Quality Report              │
# ├─────────────────────────────────────────┤
# │  Overall Score: 87 (Silver)             │
# │                                         │
# │  Breakdown:                             │
# │    Static Analysis:      92             │
# │    Trigger Accuracy:     85             │
# │    Execution Reliability: 88            │
# │    Rubric Score:         82             │
# │                                         │
# │  Trend: +5 from v1.2.0                  │
# └─────────────────────────────────────────┘
```

---

## Future Considerations

### Strategy for Building Network Effects

The more skills evaluated on Skill-Lab, the more valuable benchmarks and comparisons become.

**For Adoption:**
- Free tier for open-source skills (drives volume)
- Easy onboarding: `sklab init` generates test scaffolding
- Integration with popular skill repositories

**For Network Effects:**
- Category benchmarks require multiple skills to be meaningful
- Public leaderboards incentivize quality improvement
- Quality badges become a trust signal in marketplaces
- Shared benchmark datasets that all skills in a category should pass

### Potential Future Features (Post-MVP)

- **Skill Certification**: Skills "certified" when passing threshold
- **Automated Regression Alerts**: Notify authors when quality drops
- **Community Benchmarks**: Crowdsourced test scenarios
- **Quality API**: Marketplaces query skill quality programmatically

---

## Open Questions

1. **Hosted Service**: Should Skill-Lab offer a hosted version (sklab.dev) for badge hosting and public history, or stay CLI-only initially?

2. **Marketplace API**: What's the API contract for publishing to skillsmp.com?
