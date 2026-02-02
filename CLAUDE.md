# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python CLI tool that evaluates agent skills (SKILL.md files) through static analysis and trigger testing. Produces a 0-100 quality score based on 18 checks across 4 dimensions.

**Current Release:** v0.1.0 on PyPI includes static analysis (18 checks). See [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the version roadmap.

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
| [docs/CHECKS.md](docs/CHECKS.md) | All 18 checks with descriptions and scoring weights |
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

The codebase uses a **decorator-based auto-discovery pattern** for checks:

1. Checks are defined in `src/skill_lab/checks/static/*.py` with `@register_check` decorator
2. Importing the module registers the check to the global `CheckRegistry` singleton
3. `StaticEvaluator` imports all check modules, triggering registration
4. `registry.get_all()` returns all registered checks for execution

Same pattern applies to trace handlers (`@register_trace_handler` in `tracechecks/handlers/`).

## Common Tasks

- **Adding a check**: See [ARCHITECTURE.md - Adding a New Check](docs/ARCHITECTURE.md#adding-a-new-check)
- **Understanding data flow**: See [ARCHITECTURE.md - Data Flow](docs/ARCHITECTURE.md#data-flow)
- **Check details**: See [CHECKS.md](docs/CHECKS.md)