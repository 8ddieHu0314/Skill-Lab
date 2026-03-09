# sklab stats — Architecture & Design

Personal usage statistics for skill authors. Shows how many times skills were fired, how scores have changed over time, and how many tokens skill invocations added to context.

---

## Commands

| Command | Description |
|---|---|
| `sklab stats` | Overview: invocations this month, avg score, tokens, version history (always global) |
| `sklab stats count [--here]` | Table — skill name / use count / tokens used (current month) |
| `sklab stats score [--here]` | Table — skill name / current score / baseline score / delta |
| `sklab stats tokens [--here]` | Table — skill name / tokens per invocation / total tokens (current month) |
| `sklab setup` | Write PostToolUse hooks to Claude Code + Cursor settings files |
| `sklab _track-invocation` | Hidden — called by hooks; reads PostToolUse JSON from stdin |

`--here` scopes the output to skills whose `skill_path` is under the current git repo root (falls back to `cwd` if not in a git repo). Without `--here`, all skills across all repos are shown.

---

## Data Source

All stats are read from `~/.sklab/usage.db` (SQLite), the same database used by the existing telemetry system. No new files are created.

### Schema additions (v0.5.0)

Four columns were added to the `events` table via `ALTER TABLE ... ADD COLUMN` migration, which runs automatically in `_ensure_db()`:

```sql
ALTER TABLE events ADD COLUMN skill_name   TEXT;
ALTER TABLE events ADD COLUMN score        REAL;
ALTER TABLE events ADD COLUMN input_tokens INTEGER;
ALTER TABLE events ADD COLUMN skill_path   TEXT;
```

Old rows (written before v0.5.0) have `NULL` in these columns. The stats commands detect this via `has_old_data` in `OverviewStats` and display a notice.

`skill_path` stores the **full absolute path** of the skill directory (e.g. `/Users/me/my-project/commit`). This is what powers `--here` filtering and prevents name collisions between skills with the same directory name in different repos.

### Event types written by this feature

| `command` value | Written by | Contains |
|---|---|---|
| `evaluate` | `_with_telemetry` decorator + `push_telemetry_extra()` | `skill_name`, `score`, `skill_path` (single-skill runs only) |
| `skill-invoke` | `sklab _track-invocation` (PostToolUse hook) | `skill_name`, `input_tokens`, `skill_path` (when SKILL.md found) |

---

## Invocation Tracking

Sklab cannot observe when a skill fires in a real agent session directly. Instead it uses **PostToolUse hooks** — a Claude Code and Cursor built-in feature that runs a shell command after any tool executes.

### How it works

1. User runs `sklab setup` once.
2. sklab writes a PostToolUse hook that matches the `Skill` tool to `~/.claude/settings.json` (Claude Code) and/or `~/.cursor/hooks.json` (Cursor).
3. Every time Claude Code or Cursor invokes a skill via the `Skill` tool, the hook fires and pipes the tool's JSON to stdin of `sklab _track-invocation`.
4. `sklab _track-invocation` extracts `tool_input.skill` (the skill name), searches for the skill's SKILL.md, records the full directory path as `skill_path`, estimates tokens, and writes a `skill-invoke` row to the DB.

### Hook JSON received on stdin

```json
{
  "tool_name": "Skill",
  "tool_input": {
    "skill": "commit",
    "args": "-m 'Fix bug'"
  },
  "cwd": "/Users/you/my-project",
  "session_id": "...",
  "transcript_path": "..."
}
```

### Hook configuration written by `sklab setup`

**Claude Code** (`~/.claude/settings.json`):
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Skill",
        "hooks": [
          {
            "type": "command",
            "command": "sklab _track-invocation",
            "async": true,
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**Cursor** (`~/.cursor/hooks.json`):
```json
[
  {
    "event": "PostToolUse",
    "matcher": "Skill",
    "command": "sklab _track-invocation",
    "async": true
  }
]
```

The hook is `async: true` so Claude does not wait for it — zero latency impact.

### Codex CLI

Codex CLI has no hooks system. Invocations from Codex are not tracked and are not included in counts. Only Claude Code and Cursor counts are recorded.

---

## Token Estimation & Path Resolution

When `sklab _track-invocation` fires, it calls `_find_skill_md()` which searches for the skill's directory in these locations (in order):

1. `~/.claude/skills/<skill_name>/`
2. `~/.cursor/skills/<skill_name>/`
3. `<cwd>/.claude/skills/<skill_name>/`
4. `<cwd>/skills/<skill_name>/`

If found, the directory's absolute path is stored as `skill_path` and `estimate_tokens(content)` (the existing `len(text) // 4` heuristic from `core/tokens.py`) is applied to the SKILL.md. If not found, both `skill_path` and `input_tokens` are stored as `NULL` — that row contributes to invocation counts but is excluded from token aggregates and `--here` filtering.

This estimates the extra tokens added to context when a skill is invoked — i.e., the SKILL.md content tokens, not counting the system prompt.

---

## Score Tracking

Score is captured via a **telemetry side-channel** (`push_telemetry_extra`) in `cli.py`:

```
evaluate()
  └─ evaluator.evaluate(skill_path) → report
  └─ push_telemetry_extra(skill_name=skill_path.name,
                          score=report.quality_score,
                          skill_path=str(skill_path))
  └─ [decorator fires _record_telemetry()]
       └─ _pop_telemetry_extras() → {skill_name, score, skill_path}
       └─ record_event(command='evaluate', ..., skill_name=..., score=..., skill_path=...)
```

Only single-skill evaluate runs (not `--all`/`--repo` bulk runs) record per-skill scores.

**Baseline**: the `evaluate` row with the lowest `id` for a given `skill_name` (i.e., the first evaluate run ever for that skill).

**Current**: the `evaluate` row with the highest `id` for a given `skill_name` (most recent run).

**"new" indicator**: shown in `sklab stats score` when `MIN(id) == MAX(id)` — only one evaluate run exists, so baseline and current are the same.

---

## Module Map

| File | Responsibility |
|---|---|
| `src/skill_lab/core/stats.py` | All DB read queries; four public functions accepting optional `repo_root` |
| `src/skill_lab/core/setup.py` | Idempotent hook writing; `run_setup()`; `init_hooks_on_first_run()` |
| `src/skill_lab/reporters/stats_reporter.py` | Rich terminal display for all four stats views |
| `src/skill_lab/core/telemetry.py` | DB migration; updated `record_event()`; `push/pop_telemetry_extra()` |
| `src/skill_lab/cli.py` | `stats` sub-app (with `--here`), `setup`, `_track-invocation`, `_find_skill_md()` |
| `tests/test_stats.py` | 48 tests — query functions, CLI commands, `--here` repo filtering |
| `tests/test_setup.py` | 32 tests — setup logic, first-run auto-setup, track-invocation CLI |

---

## Design Decisions

**Why a side-channel for score tracking instead of modifying `_with_telemetry`?**
The decorator wraps all commands uniformly. Changing its signature would require updating all call sites. `push_telemetry_extra()` lets individual commands attach data without touching the decorator.

**Why `command = 'evaluate'` for score rows instead of a new command name?**
Reusing the existing command keeps one row per evaluate run. A separate `skill-evaluate` event would double the row count and complicate the Supabase sync payload.

**Why estimate tokens at hook-fire time rather than at query time?**
The SKILL.md content could change between invocation and query. Capturing at invocation time gives a historically accurate estimate.

**Why not track bulk evaluate scores?**
`sklab evaluate --all` runs multiple skills under a single telemetry event. Injecting per-skill rows inside the bulk loop would require calling `record_event()` directly (bypassing the decorator) and mix scoring rows with the overall duration row. Deferred to a future version.

**Why store `skill_path` as a full absolute path?**
Relative paths would be ambiguous across different working directories. Full paths make `--here` filtering unambiguous via a simple SQL `LIKE '/repo/root/%'` clause, and allow future features like per-repo dashboards. Skills without a resolvable path (e.g. Codex invocations) store `NULL` and are excluded from `--here` results — they still appear in global views.

**Why does `--here` fall back to `cwd` when not in a git repo?**
Skills can exist outside git repos. Falling back to `cwd` ensures `--here` still works meaningfully rather than silently returning everything or nothing.
