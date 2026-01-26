# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python CLI tool for evaluating agent skills (SKILL.md files) through static analysis and quality checks. It parses YAML frontmatter and markdown content from skill definitions, runs 20 static checks across 4 dimensions (structure, naming, description, content), and produces a weighted 0-100 quality score.

## Commands

```bash
# Install
pip install -e ".[dev]"

# Run CLI
skill-lab evaluate ./my-skill           # Console output
skill-lab evaluate ./my-skill -f json   # JSON output
skill-lab validate ./my-skill           # Quick validation (exit code 0/1)
skill-lab list-checks                   # List all checks

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
3. Implement `run(skill: Skill) -> CheckResult` using `self._pass()` or `self._fail()`
4. Add the `@register_check` decorator - no other wiring needed

**Data Flow**: `CLI` → `StaticEvaluator.evaluate()` → `parse_skill()` → run all checks → `calculate_score()` → `EvaluationReport` → reporter (Console/JSON)

**Key Models** (`core/models.py`):
- `Skill`: Parsed skill with metadata, body, and parse errors
- `CheckResult`: Individual check outcome with severity/dimension
- `EvaluationReport`: Complete evaluation with score and summary
- `Severity`: ERROR (must fix), WARNING (should fix), INFO (suggestion)
- `EvalDimension`: STRUCTURE, NAMING, DESCRIPTION, CONTENT
