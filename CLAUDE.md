# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python CLI tool that evaluates agent skills (SKILL.md files) through static analysis and trigger testing. Produces a 0-100 quality score based on 21 checks across 4 dimensions.

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
| [docs/CHECKS.md](docs/CHECKS.md) | All 21 checks with descriptions and scoring weights |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Roadmap and phase status |

**After code changes**, update relevant docs:
- `ARCHITECTURE.md` - New modules, directory changes, CLI commands
- `CHECKS.md` - Check additions/modifications
- `IMPLEMENTATION_PLAN.md` - Phase status updates

## Quick Start

```bash
pip install -e ".[dev]"                 # Install with dev dependencies
sklab evaluate ./my-skill               # Run evaluation
pytest tests/ -v                        # Run all tests
pytest tests/test_naming.py -v          # Run single test file
pytest tests/test_naming.py::test_name -v  # Run single test
mypy src/                               # Type check (strict mode)
ruff check src/                         # Lint
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


## Useful Sources for References

- [OpenAI: How to Evaluate Agent Skills](https://developers.openai.com/blog/eval-skills/) - Criteria for skill evaluation (focus on 1-5 for deterministic checks), treat is as a concrete blueprint for how to implement those checks
- [Medium: How to Evaluate AI Agent Skills Without Relying on Vibes](https://jpcaparas.medium.com/how-to-evaluate-ai-agent-skills-without-relying-on-vibes-9a5764ad18c4) - Refined version of OpenAI's approach, treat is as a high-level framing of what to check deterministically
- [Agent Skills Specification](https://agentskills.io/specification) - Official specification for SKILL.md format
