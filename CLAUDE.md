# CLAUDE.md

Quick reference for Claude Code when working in this repository.

## Project Overview

Python CLI tool that evaluates agent skills (SKILL.md files) through static analysis and trigger testing. Produces a 0-100 quality score based on 21 checks across 4 dimensions.

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
pip install -e ".[dev]"                 # Install
skill-lab evaluate ./my-skill           # Run evaluation
pytest tests/ -v && mypy src/           # Run tests + type check
```

For full CLI options, see [ARCHITECTURE.md - CLI Commands](docs/ARCHITECTURE.md#cli-commands-clipy).

## Common Tasks

- **Adding a check**: See [ARCHITECTURE.md - Adding a New Check](docs/ARCHITECTURE.md#adding-a-new-check)
- **Understanding data flow**: See [ARCHITECTURE.md - Data Flow](docs/ARCHITECTURE.md#data-flow)
- **Check details**: See [CHECKS.md](docs/CHECKS.md)
