# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Python CLI tool that evaluates agent skills (SKILL.md files) via static analysis, trigger testing, and LLM-based test generation. Produces a 0-100 score across 29 checks (structure:7, naming:1, schema:9, content:11, security:1) / 5 dimensions.

## Naming

| Name | Usage |
|------|-------|
| **Skill-Lab** | GitHub repo / project name |
| **skill-lab** | PyPI package (`pip install skill-lab`) |
| **sklab** | CLI command (`sklab evaluate ./my-skill`) |

## Docs

| Document | Contents |
|----------|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Tech stack, data flow, CLI commands, check systems, design patterns |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Vision, roadmap, design decisions |
| [docs/SECURITY.md](docs/SECURITY.md) | 5-layer security scan details |
| [docs/PRIVACY.md](docs/PRIVACY.md) | Telemetry & privacy policy |
| [docs/versions/](docs/versions/) | Per-version specs (v0.1.0–v1.0.0) |

After code changes: update `ARCHITECTURE.md` (modules/CLI) and the relevant `docs/versions/vX.X.X.md`.

ALWAYS READ THE DOCS BEFORE ACTIONING

## Commands

```bash
pip install -e ".[dev]"       # install with dev deps
sklab evaluate ./my-skill     # static analysis
sklab check                   # quick pass/fail
sklab info ./my-skill         # metadata + token estimates
sklab prompt ./skill-a        # export skill as XML prompt
sklab trigger                 # run trigger tests (requires Claude CLI)
sklab generate                # generate trigger tests via LLM (requires anthropic)
sklab stats                   # usage statistics
sklab setup                   # configure hooks for Claude Code/Cursor
sklab scan ./my-skill         # security scan (BLOCK/SUS/ALLOW)
sklab list-checks             # browse all checks (--spec-only, --suggestions-only)
pytest tests/ -v                            # run all tests
pytest tests/test_checks.py -v              # run single test file
pytest tests/test_checks.py -k "keyword" -v # filter by keyword
mypy src/                     # type check
ruff check src/ && ruff format src/
/verify                       # runs all of the above (pytest, mypy, ruff check, ruff format)
```

## Critical Architecture Notes

- **Two check systems**: behavioral (`@register_check` classes in `structure.py`, `naming.py`, `content.py`) and schema-based (`FieldRule` in `schema.py` — append to add a check, no class needed). See ARCHITECTURE.md for full details.
- **Side-effect registration**: `StaticEvaluator.__init__()` imports check modules (`content`, `naming`, `schema`, `security`, `structure`) to trigger `@register_check` decorators. All checks must be registered before `registry.get_all()` is called.
- **Sync requirement**: `SPEC_FRONTMATTER_FIELDS` in `structure.py` must stay in sync with `FRONTMATTER_SCHEMA` in `schema.py`.
- **Scoring**: Weighted across 5 dimensions (Structure, Naming, Description, Content, Execution) by severity (HIGH > MEDIUM > LOW). Execution is trace-based (`tracechecks/`) and scored separately. See `scoring.py` for exact weights.
- **Anthropic SDK**: `anthropic` is a required dependency, used by `sklab generate` for LLM-based trigger test generation.
- **Test fixtures**: `tests/fixtures/skills/` — each subdirectory is a mock skill with `SKILL.md`.
- **Trigger test files**: `.sklab/tests/triggers.yaml`.

## Workflow Orchestration

### 1. Plan Node Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After corrections from the user: update `.claude/.tasks/lessons.md`
- Only capture lessons that are reusable in future sessions (tool quirks, API gotchas, patterns). Skip one-off mistakes or context-specific decisions.
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

### CLI Patterns

- Commands are split into modules under `commands/` (evaluate, trigger, generate, info, stats, telemetry, setup). Shared helpers (`_resolve_skill_path()`, `_cli_error_handler()`) live in `cli.py`.
- Exit codes: 0 = success, 1 = failure (spec-required check failed or error)
- Custom exceptions inherit from `SkillLabError` in `core/exceptions.py` (`ParseError`, `ValidationError`, `ConfigurationError`, `GenerationError`)

## Code Style

- **Line length**: 100 characters (ruff formatter)
- **Type checking**: mypy strict mode — all functions need type annotations
- **Python**: 3.10+ (no 3.9 syntax)
- **Data models**: frozen dataclasses (`@dataclass(frozen=True)`) for immutability
- **CI matrix**: Python 3.10–3.13 on Ubuntu/macOS/Windows — code must pass all three

---

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `.claude/.tasks/lessons.md` after corrections — reusable lessons only and mistakes the AI has made

---

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
