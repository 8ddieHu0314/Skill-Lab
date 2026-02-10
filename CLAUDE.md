# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python CLI tool that evaluates agent skills (SKILL.md files) through static analysis, trigger testing, and LLM-based test generation. Produces a 0-100 quality score based on 19 checks across 4 dimensions.

**Current Release:** v0.3.0 on PyPI includes static analysis (19 checks), trigger testing, and `sklab generate` for LLM-based trigger test generation. See [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the version roadmap.

## Naming Convention

| Name | Usage |
|------|-------|
| **Skill-Lab** | GitHub repo name, project name |
| **skill-lab** | PyPI package name |
| **sklab** | CLI command |

- GitHub URLs use `Skill-Lab`: `github.com/8ddieHu0314/Skill-Lab`
- PyPI/pip uses `skill-lab`: `pip install skill-lab`
- CLI command is `sklab`: `sklab evaluate ./my-skill`

## Documentation

| Document | Contents |
|----------|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Tech stack, data flow, CLI commands, design patterns |
| [docs/CHECKS.md](docs/CHECKS.md) | All 19 checks with descriptions and scoring weights |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Vision, roadmap overview, design decisions |
| [docs/versions/](docs/versions/) | Detailed specs for each version (v0.1.0 - v1.0.0) |

**After code changes**, update relevant docs:
- `ARCHITECTURE.md` - New modules, directory changes, CLI commands
- `CHECKS.md` - Check additions/modifications
- `docs/versions/vX.X.X-*.md` - Version-specific deliverables and status

## Quick Start

```bash
pip install -e ".[dev]"                    # Install with dev dependencies
sklab -v                                   # Show version
sklab evaluate ./my-skill                  # Run static analysis on specific skill
sklab evaluate                             # Run static analysis on current directory
sklab evaluate -s                          # Spec-required checks only
sklab validate                             # Quick pass/fail validation
sklab trigger                              # Run trigger tests (requires Claude CLI)
sklab generate                             # Generate trigger tests via LLM (requires anthropic)
sklab generate --model claude-sonnet-4-5-20250929  # Use a specific model
pytest tests/ -v                           # Run all tests
pytest tests/test_naming.py -v             # Run single test file
pytest tests/test_naming.py::test_name -v  # Run single test
pytest tests/ --cov=skill_lab              # Run with coverage
mypy src/                                  # Type check (strict mode)
ruff check src/                            # Lint
ruff format src/                           # Format code
```

For full CLI options, see [ARCHITECTURE.md - CLI Commands](docs/ARCHITECTURE.md#cli-commands-clipy).

## Key Architecture

### Two Check Systems (19 total: 10 spec-required, 9 quality suggestions)

The codebase has **two distinct patterns** for defining static checks:

**1. Behavioral checks** — hand-written classes with `@register_check` decorator:
- `structure.py` (5 checks): `SkillMdExistsCheck`, `ValidFrontmatterCheck`, `StandardFrontmatterFieldsCheck`, etc.
- `naming.py` (1 check): `MatchesDirectoryCheck`
- `content.py` (4 checks): `HasExamplesCheck`, `LineBudgetCheck`, etc.

**2. Schema-based checks** — declarative `FieldRule` definitions in `schema.py` (9 checks):
- Each `FieldRule` in `FRONTMATTER_SCHEMA` list describes a single constraint (field name, type, max length, regex, etc.)
- `_make_schema_check()` factory creates a concrete `StaticCheck` subclass per rule at import time
- `_validate_rule()` engine interprets the rule and produces `CheckResult` objects
- To add a schema check: append a `FieldRule` to `FRONTMATTER_SCHEMA` — no class needed

### Auto-Discovery Pattern

1. Importing a check module registers checks to the global `CheckRegistry` singleton
2. `StaticEvaluator` imports all check modules (`content`, `naming`, `schema`, `structure`), triggering registration
3. `registry.get_all()` returns all registered check classes for execution
4. `Registry.register()` raises `ValueError` on duplicate `check_id`

Same pattern applies to trace handlers (`@register_trace_handler` in `tracechecks/handlers/`).

### Sync Requirements

- `SPEC_FRONTMATTER_FIELDS` set in `structure.py` must stay in sync with `FRONTMATTER_SCHEMA` in `schema.py` when adding new frontmatter fields

### Optional Dependencies

- `anthropic` is an optional dep: `pip install skill-lab[generate]`
- `TriggerGenerator` in `triggers/generator.py` is deliberately **NOT** imported in `triggers/__init__.py` to avoid import errors when `anthropic` is not installed
- Guard pattern: lazy import inside the `generate` CLI command only

## Testing Conventions

- **Fixtures** live in `tests/fixtures/skills/` — each subdirectory is a mock skill with `SKILL.md`
- **Schema-based checks**: use `_get_check(check_id)` helper (registry lookup) in `test_checks.py`
- **Behavioral checks**: import the class directly (e.g., `from skill_lab.checks.static.naming import MatchesDirectoryCheck`)
- **Trigger test files**: `.skill-lab/tests/triggers.yaml` (migrated from `tests/` in v0.3.0)

## Common Tasks

- **Adding a behavioral check**: See [ARCHITECTURE.md - Adding a New Check](docs/ARCHITECTURE.md#adding-a-new-check)
- **Adding a schema check**: Append a `FieldRule` to `FRONTMATTER_SCHEMA` in `schema.py`
- **Understanding data flow**: See [ARCHITECTURE.md - Data Flow](docs/ARCHITECTURE.md#data-flow)
- **Check details**: See [CHECKS.md](docs/CHECKS.md)