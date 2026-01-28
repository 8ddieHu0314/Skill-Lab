# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python CLI tool for evaluating agent skills (SKILL.md files) through static analysis, trigger testing, and quality checks. It parses YAML frontmatter and markdown content from skill definitions, runs 21 static checks across 4 dimensions (structure, naming, description, content), and produces a weighted 0-100 quality score. It also supports trigger testing to verify skills activate correctly with different prompt types.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Tech stack and system architecture
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) - Roadmap and implementation details (always keep updated)
- [docs/CHECKS.md](docs/CHECKS.md) - List of all quality checks with descriptions

**IMPORTANT**: After any code modification, review and update these documentation files:
- `docs/ARCHITECTURE.md` - Update if adding new modules, changing directory structure, modifying data flow, or adding CLI commands
- `docs/CHECKS.md` - Update if adding, removing, or modifying static checks
- `docs/IMPLEMENTATION_PLAN.md` - Update phase status and deliverable checkboxes when completing features

## Commands

```bash
# Install
pip install -e ".[dev]"

# Run CLI
skill-lab evaluate ./my-skill           # Console output
skill-lab evaluate ./my-skill -f json   # JSON output
skill-lab evaluate ./my-skill -s        # Spec-required checks only
skill-lab validate ./my-skill           # Quick validation (exit code 0/1)
skill-lab list-checks                   # List all checks
skill-lab test-triggers ./my-skill      # Run trigger tests
skill-lab test-triggers ./my-skill -r codex  # Specify runtime

# Development
pytest tests/ -v                    # Run all tests
pytest tests/test_checks.py -v      # Run single test file
pytest tests/ --cov=skill_lab  # With coverage
mypy src/                           # Type checking
ruff check src/                     # Linting
```

## Architecture

**Check Registration Pattern**: Checks are auto-registered via the `@register_check` decorator which adds them to a global `CheckRegistry` singleton. The `StaticEvaluator` imports check modules at the top of `static_evaluator.py` to trigger registration, then retrieves all checks from the registry at runtime.

**Adding a New Check**:
1. Create a class extending `StaticCheck` in the appropriate `checks/static/` module
2. Define class attributes: `check_id`, `check_name`, `description`, `severity`, `dimension`
3. Set `spec_required = True` if check enforces the Agent Skills spec (default `False`)
4. Implement `run(skill: Skill) -> CheckResult` using `self._pass()` or `self._fail()`
5. Add the `@register_check` decorator - no other wiring needed

**Data Flow**: `CLI` → `StaticEvaluator.evaluate()` → `parse_skill()` → run all checks → `calculate_score()` → `EvaluationReport` → reporter (Console/JSON)

**Key Models** (`core/models.py`):
- `Skill`: Parsed skill with metadata, body, and parse errors
- `CheckResult`: Individual check outcome with severity/dimension
- `EvaluationReport`: Complete evaluation with score and summary
- `Severity`: ERROR (must fix), WARNING (should fix), INFO (suggestion)
- `EvalDimension`: STRUCTURE, NAMING, DESCRIPTION, CONTENT

**Scoring Weights**: Final score is a weighted average across dimensions:
- Dimension weights: STRUCTURE 30%, NAMING 20%, DESCRIPTION 25%, CONTENT 25%
- Severity weights: ERROR 1.0, WARNING 0.5, INFO 0.25

**Trigger Testing**: Tests whether skills activate correctly for different prompt types:
- `TriggerEvaluator`: Orchestrates test execution through runtime adapters
- `RuntimeAdapter`: Abstract base class for Codex/Claude CLI integration
- `TraceAnalyzer`: Parses execution traces to detect skill invocations
- Test definitions: `tests/scenarios.yaml` (Given/When/Then DSL) or `tests/triggers.yaml` (simple format)
- Trigger types: EXPLICIT ($ prefix), IMPLICIT (scenario), CONTEXTUAL (noisy), NEGATIVE (should not trigger)
