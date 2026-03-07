# CLAUDE.md

Python CLI tool that evaluates agent skills (SKILL.md files) via static analysis, trigger testing, and LLM-based test generation. Produces a 0-100 score across 28 checks / 4 dimensions.

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
| [docs/versions/](docs/versions/) | Per-version specs (v0.1.0–v1.0.0) |

After code changes: update `ARCHITECTURE.md` (modules/CLI) and the relevant `docs/versions/vX.X.X.md`.

## Commands

```bash
pip install -e ".[dev]"       # install with dev deps
sklab evaluate ./my-skill     # static analysis
sklab validate                # quick pass/fail
sklab info ./my-skill         # metadata + token estimates
sklab prompt ./skill-a        # export skill as XML prompt
sklab trigger                 # run trigger tests (requires Claude CLI)
sklab generate                # generate trigger tests via LLM (requires anthropic)
pytest tests/ -v              # run tests
mypy src/                     # type check
ruff check src/ && ruff format src/
```

## Critical Architecture Notes

- **Two check systems**: behavioral (`@register_check` classes in `structure.py`, `naming.py`, `content.py`) and schema-based (`FieldRule` in `schema.py` — append to add a check, no class needed). See ARCHITECTURE.md for full details.
- **Sync requirement**: `SPEC_FRONTMATTER_FIELDS` in `structure.py` must stay in sync with `FRONTMATTER_SCHEMA` in `schema.py`.
- **Optional dep**: `anthropic` is not imported in `triggers/__init__.py` — only lazy-imported inside the `generate` CLI command. Install via `pip install skill-lab[generate]`.
- **Test fixtures**: `tests/fixtures/skills/` — each subdirectory is a mock skill with `SKILL.md`.
- **Trigger test files**: `.skill-lab/tests/triggers.yaml`.

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