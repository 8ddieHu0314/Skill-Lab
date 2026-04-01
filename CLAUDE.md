# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Python CLI tool (v0.6.0) that evaluates agent skills (SKILL.md files) via static analysis, LLM-as-judge quality review, trigger testing, and LLM-based test generation. Produces a 0-100 static score across 37 checks (structure:13, naming:3, description:3, content:13, security:5) / 5 dimensions, plus a 0-100 LLM judge score across 9 criteria / 2 axes (Activation Quality + Instruction Quality).

## Attribution

NEVER include Co-Authored-By lines, "Generated with Claude Code", or any AI co-authorship attribution in commit messages, PR descriptions, PR reviews, or any other output.

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
sklab                         # auto-scan repo + getting started guide (no subcommand)
sklab evaluate ./my-skill     # static analysis + LLM quality review (--optimize to chain into optimizer)
sklab evaluate --all          # evaluate every skill in CWD (also: --repo for git root)
sklab check                   # quick pass/fail (exit 0/1, good for CI)
sklab info ./my-skill         # metadata + token estimates
sklab prompt ./skill-a        # export skill as XML prompt
sklab trigger                 # run trigger tests (requires Claude CLI, --provider local|docker)
sklab generate                # generate trigger tests via LLM (multi-provider)
sklab optimize ./my-skill     # LLM-powered SKILL.md optimization (multi-provider)
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

Batch flags available on `evaluate`, `check`, and `scan`: `--all` (CWD) and `--repo` (git root).

## Critical Architecture Notes

See `docs/ARCHITECTURE.md` for full directory structure and data flow diagrams.

### Check System

- **Two check systems**: behavioral (`@register_check` classes in `structure.py`, `naming.py`, `content.py`, `security.py`) and schema-based (`FieldRule` in `schema.py` — append to add a check, no class needed). Per-file counts: structure:9, schema:9, content:13, security:5, naming:1. Dimension counts differ (checks can map to any dimension).
- **Adding a schema check**: append a `FieldRule` to `FRONTMATTER_SCHEMA` list in `schema.py` — no class needed. The `_make_schema_check()` factory auto-generates a registered class per rule.
- **Side-effect registration**: `StaticEvaluator.__init__()` imports check modules (`content`, `naming`, `schema`, `security`, `structure`) to trigger `@register_check` decorators. All checks must be registered before `registry.get_all()` is called.
- **Sync requirement**: `SPEC_FRONTMATTER_FIELDS` in `structure.py` must stay in sync with `FRONTMATTER_SCHEMA` in `schema.py`.
- **Security checks**: `security.py` has a single `SecurityScanCheck` class that registers 5 separate checks (injection, evaluator, unicode, yaml, size) via dynamic class creation — same pattern as schema checks.
- **Check count**: When adding/removing checks, update the "37 checks" count in this file's opening line and run `/update-counts` to sync docs and tests.

### Trace Checks & Runtimes

- **Trace checks**: `tracechecks/` is a parallel registration system using `@register_trace_handler` decorator and `TraceCheckRegistry`. 5 handlers: `command_presence`, `file_creation`, `event_sequence`, `loop_detection`, `efficiency`. Scored under the Execution dimension.
- **Runtimes**: `runtimes/` provides adapters for running trigger tests against live LLMs — `claude_runtime.py` (Claude Code CLI) and `codex_runtime.py` (OpenAI Codex). Both extend `base.py` ABC.
- **Execution providers**: `providers/` controls WHERE agents run. `LocalProvider` (default) creates an isolated temp directory per test with the skill copied into `.claude/skills/`. `DockerProvider` (planned) will run tests inside containers. Provider is orthogonal to runtime — `RuntimeAdapter` = HOW (CLI args, trace format), `ExecutionProvider` = WHERE (temp dir, Docker).
- **Scoring**: Weighted across 5 dimensions (Structure, Naming, Description, Content, Execution) by severity (HIGH > MEDIUM > LOW). Execution is trace-based and scored separately. See `scoring.py` for exact weights.

### LLM Features

- **LLM config**: `core/llm.py` defines the default model (`claude-haiku-4-5-20251001`), pricing table, `GenerationUsage` class, and the `LLMProvider` abstraction (Anthropic, OpenAI, Gemini). Model resolution: `--model` flag > `SKLAB_MODEL` env var > default. Provider is auto-detected from model ID prefix (`gpt-*`/`o3-*` → OpenAI, `gemini-*` → Gemini, else Anthropic). When adding new models, update `_PRICING` dict in `core/llm.py`.
- **LLM-as-judge**: `judge/judge.py` (SkillJudge) + `judge/rubric.md` (system prompt with 9-criterion rubric). Runs automatically during `sklab evaluate` when API key is available. `--skip-review` to disable, `--model` to choose provider. Scores: Activation Quality (4 criteria) + Instruction Quality (5 criteria), each 0-4, normalized to 0-100%. Verdict bands: 90+ Excellent, 75-89 Good, 50-74 Needs work, <50 Poor.
- **Optimizer**: `optimizer/optimizer.py` (SkillOptimizer) + `optimizer/optimize_skill.md` (system prompt). `optimize_from_history()` reads eval history instead of running its own evaluation — sees both static failures AND judge feedback. Chained via `sklab evaluate --optimize` or standalone `sklab optimize`.
- **LLM SDKs**: `anthropic`, `openai`, and `google-generativeai` are all required dependencies. API key env vars: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`.

### Data Persistence

- **Shared paths**: `core/constants.py` defines all `.sklab/` paths (`SKILLLAB_DIR`, `EVALS_DIR`, `TESTS_DIR`, `TRACES_DIR`, `CONFIG_FILE`) and `~/.sklab/` home paths. Always use these constants, not hardcoded strings.
- **Eval history**: `core/eval_history.py` persists full evaluation results (static + judge) to `.sklab/evals/{timestamp}.json`. Capped at 20 files with automatic pruning. Timestamps are UTC-normalized. The optimizer reads the latest eval file via `load_latest_eval()`.
- **Per-skill config**: `core/skill_config.py` manages `.sklab/config.yaml` — stores `last-review` (judge results) and other per-skill settings.
- **Trigger test files**: `.sklab/tests/triggers.yaml`.
- **`.env` support**: `python-dotenv` loads `.env` from CWD at CLI startup (`cli.main()`). Real env vars override `.env` values (`override=False`). The `pyproject.toml` entry point is `cli:main` (not `cli:app`) so dotenv loads before Typer dispatch.

### Testing

- **Test fixtures**: `tests/fixtures/skills/` — each subdirectory is a mock skill with `SKILL.md`. Shared pytest fixtures (`fixtures_dir`, `skills_dir`, `valid_skill_path`, `evaluator`) are in `tests/conftest.py`.
- **Test helper**: `_get_check(check_id)` in `test_checks.py` retrieves schema-based checks from the registry; behavioral checks are imported directly as classes.

### CLI Patterns

- Commands are split into modules under `commands/` (evaluate, trigger, generate, optimize, info, stats, telemetry, setup, scan). Shared helpers (`_resolve_skill_path()`, `_cli_error_handler()`) live in `cli.py`.
- **Reporters**: `reporters/` bridges evaluators to output — `console_reporter.py` (Rich terminal), `json_reporter.py` (JSON), `stats_reporter.py` (stats tables). Commands pick the reporter based on `--format`.
- Exit codes: 0 = success, 1 = failure (spec-required check failed or error)
- Custom exceptions inherit from `SkillLabError` in `core/exceptions.py` (`ParseError`, `ValidationError`, `ConfigurationError`, `GenerationError`)
- **CI env var**: Set `SKLAB_NO_ANALYTICS=1` to suppress the telemetry opt-in prompt (used in CI workflow and tests).

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

### Task Tracking
- Write plan to `tasks/todo.md` with checkable items, mark items complete as you go
- Capture reusable lessons in `.claude/.tasks/lessons.md` after corrections

## Code Style

- **Line length**: 100 characters (ruff formatter)
- **Type checking**: mypy strict mode — all functions need type annotations
- **Python**: 3.10+ (no 3.9 syntax)
- **Data models**: frozen dataclasses (`@dataclass(frozen=True)`) for immutability
- **CI matrix**: Python 3.10–3.13 on Ubuntu/macOS/Windows — code must pass all three
