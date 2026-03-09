# DEV_STATS.md — Usage Analytics & Telemetry

Reference for how sklab collects, stores, and syncs usage data.

---

## Overview

Every sklab command optionally records an event. Data flows:

```
sklab command
     │
     ▼
init_telemetry()          ← first interactive run: shows opt-out notice
     │
     ▼
[command executes]
     │
     ▼ (finally block in _with_telemetry decorator)
_record_telemetry()
     ├── record_event()   → write rows to ~/.sklab/usage.db (SQLite)
     │                    → _sync_to_endpoint() (fire-and-forget POST)
     ├── record_error()   → write to error_events if exception was raised
     └── check_for_update() → fetch pypi.org once/day, nudge to stderr if newer
```

All network calls use a short timeout (2–3 s) and swallow every exception. A network failure or endpoint outage never crashes the CLI.

---

## User Consent

**Opt-out model** — telemetry is enabled by default on first interactive run. A notice is printed; no confirmation required.

### Opt-out mechanisms

| Method | Effect |
|--------|--------|
| `SKLAB_NO_ANALYTICS=1` env var | Disables all telemetry for that process; config unchanged |
| `DO_NOT_TRACK=1` env var | Same (cross-tool standard) |
| Edit `~/.sklab/config.json` | Set `"analytics_enabled": false` manually to re-enable or disable permanently |
| Non-interactive stdout (CI, pipe) | Auto-disabled on first run; config not written |

> Opted-out users get **no local storage** and no sync. `sklab stats` shows no data.

---

## Config File

**Path:** `~/.sklab/config.json`

```json
{
  "user_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "analytics_enabled": true,
  "last_version_check": "2026-03-09T12:00:00+00:00",
  "latest_version": "0.5.0"
}
```

| Field | Description |
|-------|-------------|
| `user_uuid` | Random UUID generated on first run. The `install_uuid` in all tables. |
| `analytics_enabled` | Written at first run; controls all local storage and sync. |
| `last_version_check` | ISO 8601 UTC. Rate-limits PyPI checks to once per day. |
| `latest_version` | Cached PyPI result for version nudge. |

---

## Local SQLite Schema

**Path:** `~/.sklab/usage.db`

Four normalized tables replaced the old flat `events` table (which is kept untouched for backward compatibility).

### `installs` — one row per install UUID

| Column | Type | Description |
|--------|------|-------------|
| `install_uuid` | TEXT PK | Anonymous UUID from config.json |
| `first_seen_at` | TEXT | ISO 8601 UTC of first recorded run |
| `last_seen_at` | TEXT | ISO 8601 UTC of most recent run |
| `run_count` | INTEGER | Total opted-in runs (incremented on upsert) |
| `sklab_version` | TEXT | Version at last run |
| `os` | TEXT | `platform.system()` — `Darwin`, `Linux`, `Windows` |
| `python_version` | TEXT | `major.minor` only (e.g. `3.12`) |
| `is_ci` | INTEGER | `1` if a CI env var was detected |
| `ci_provider` | TEXT | Provider name or NULL — see CI detection below |
| `synced` | INTEGER | `0` = pending, `1` = POSTed successfully |

### `command_events` — one row per CLI invocation

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `install_uuid` | TEXT | FK → installs |
| `session_uuid` | TEXT | UUID generated once per process; groups commands in one terminal session |
| `sklab_version` | TEXT | Version at time of run |
| `command` | TEXT | Command name: `evaluate`, `validate`, `trigger`, `generate`, `info`, `prompt`, `stats-count`, etc. |
| `subcommand` | TEXT | Reserved; currently NULL |
| `flags` | TEXT | JSON array of boolean flags set to True (e.g. `["--verbose","--spec-only"]`). Names only — no values. |
| `duration_ms` | REAL | Wall-clock ms |
| `exit_code` | INTEGER | `0` = success |
| `success` | INTEGER | `1` if exit_code == 0 |
| `is_ci` | INTEGER | `1` if CI detected |
| `ci_provider` | TEXT | Provider name or NULL |
| `timestamp` | TEXT | ISO 8601 UTC |
| `synced` | INTEGER | `0` = pending, `1` = synced |

### `skill_events` — one row per skill evaluation or invocation

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `command_event_id` | INTEGER | FK → command_events.id (nullable) |
| `install_uuid` | TEXT | FK → installs |
| `skill_name` | TEXT | Skill name from frontmatter or directory name |
| `skill_version` | TEXT | Skill version from frontmatter |
| `skill_source` | TEXT | Reserved |
| `skill_path` | TEXT | **Local only — never synced to endpoint** |
| `score` | REAL | Evaluation score 0–100 (evaluate runs only) |
| `model_name` | TEXT | Model used for invocation |
| `input_tokens` | INTEGER | Input token count |
| `output_tokens` | INTEGER | Output token count |
| `step_count` | INTEGER | Steps in agent run |
| `tool_call_count` | INTEGER | Tool calls in agent run |
| `execution_time_ms` | REAL | Skill execution wall-clock time |
| `success` | INTEGER | `1` = succeeded |
| `timestamp` | TEXT | ISO 8601 UTC |
| `synced` | INTEGER | `0` = pending, `1` = synced |

### `error_events` — one row per caught exception

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `command_event_id` | INTEGER | FK → command_events.id (nullable) |
| `install_uuid` | TEXT | FK → installs |
| `error_type` | TEXT | Exception class name only (e.g. `FileNotFoundError`) — **no message** |
| `error_module` | TEXT | Module where the exception class is defined |
| `command` | TEXT | Command that raised the exception |
| `sklab_version` | TEXT | Version at time of error |
| `timestamp` | TEXT | ISO 8601 UTC |
| `synced` | INTEGER | `0` = pending, `1` = synced |

### Legacy `events` table

The old flat table is preserved so pre-migration data survives. `sklab stats` warns users when it detects rows here via `has_old_data`. No new rows are written to it.

---

## What Is Collected vs. Not Collected

| Collected | Not Collected |
|-----------|---------------|
| Command names | Skill content or prompts |
| Flag names (boolean, True only) | Flag values |
| Duration, exit code, success | Hostnames, usernames |
| OS, Python version, sklab version | Full Python version string |
| Session UUID (groups commands in one shell session) | Environment variable values |
| CI environment + provider name | Error messages or stack traces |
| Skill names, versions, scores | File paths (stored locally, never synced) |
| Token counts (input + output) | |
| Error class name + module | |
| Install lifecycle (first seen, last seen, run count) | |

---

## CI Detection

Detected via env vars in priority order:

| Env Var | Provider |
|---------|----------|
| `GITHUB_ACTIONS` | `github_actions` |
| `GITLAB_CI` | `gitlab_ci` |
| `TRAVIS` | `travis` |
| `CIRCLECI` | `circleci` |
| `JENKINS_URL` | `jenkins` |
| `BUILDKITE` | `buildkite` |
| `TF_BUILD` | `azure_pipelines` |
| `BITBUCKET_BUILD_NUMBER` | `bitbucket` |
| `CI=true` (any case) | NULL (generic CI) |

---

## Sync Behaviour

All four tables are batched into a single POST per sync attempt:

```json
{
  "installs":       [...],
  "command_events": [...],
  "skill_events":   [...],   // skill_path excluded
  "error_events":   [...]
}
```

**Endpoint:** `https://api.skill-lab.dev/v1/events`

Rows with `synced = 0` are retried on the next run. `skill_path` is stored locally in `skill_events` but stripped from the sync payload.

```
Run 1 (online)  → write rows → POST → synced = 1
Run 2 (offline) → write rows → POST fails → synced = 0
Run 3 (online)  → write rows → POST rows 2+3 → all synced = 1
```

---

## Useful SQLite Queries

```bash
# Recent command history
sqlite3 ~/.sklab/usage.db \
  "SELECT command, duration_ms, exit_code, timestamp FROM command_events ORDER BY id DESC LIMIT 20;"

# Skills invoked this month
sqlite3 ~/.sklab/usage.db \
  "SELECT se.skill_name, COUNT(*) FROM skill_events se
   JOIN command_events ce ON se.command_event_id = ce.id
   WHERE ce.command = 'skill-invoke'
   GROUP BY se.skill_name ORDER BY 2 DESC;"

# Score history per skill
sqlite3 ~/.sklab/usage.db \
  "SELECT skill_name, score, timestamp FROM skill_events WHERE score IS NOT NULL ORDER BY id;"

# Recent errors
sqlite3 ~/.sklab/usage.db \
  "SELECT error_type, error_module, command, timestamp FROM error_events ORDER BY id DESC LIMIT 10;"

# Install stats
sqlite3 ~/.sklab/usage.db \
  "SELECT install_uuid, run_count, first_seen_at, last_seen_at, sklab_version FROM installs;"

# Unsynced rows
sqlite3 ~/.sklab/usage.db \
  "SELECT 'command_events', COUNT(*) FROM command_events WHERE synced=0
   UNION ALL SELECT 'skill_events', COUNT(*) FROM skill_events WHERE synced=0
   UNION ALL SELECT 'error_events', COUNT(*) FROM error_events WHERE synced=0;"
```

---

## Version Update Check

`check_for_update()` fetches `https://pypi.org/pypi/skill-lab/json` and compares against `__version__`. Cached in config for 24 hours. If newer, prints to **stderr** after command output (safe for `--json` consumers):

```
sklab 0.6.0 is available (you have 0.5.0). Run: pip install --upgrade skill-lab
```

Runs regardless of analytics opt-in.

---

## Possible Analytics

### Command Usage
- Which commands are used most/least (evaluate, validate, trigger, generate, etc.)
- Which flags are most commonly combined together
- Average command duration by command type
- Success/failure rates per command
- How command usage changes over time (growth, decline)

### Skill Performance
- Score distribution across all skill evaluations (histogram of 0–100 scores)
- Score trends over time per skill — are skills improving after edits?
- Which skills fail most often or score lowest
- Token usage per skill (input + output) — which skills are most expensive?
- Step count and tool call count distributions — which skills are most complex to run?

### User Retention & Engagement
- Daily/weekly active installs
- Run frequency per install (heavy vs. casual users)
- Time between first seen and last seen (how long users stick around)
- Drop-off: installs that ran once vs. multiple times

### Error Analysis
- Most common error types and which commands trigger them
- Which sklab versions introduced or fixed errors
- Error rate over time (regressions after releases)

### Adoption & Environment
- OS breakdown (macOS vs. Linux vs. Windows)
- Python version distribution across users
- CI vs. local usage split, and which CI providers dominate
- Version adoption rate after a new release (how quickly users upgrade)

### Session Behavior
- How many commands are run per session (session depth)
- Common command sequences within a session (e.g., info → evaluate → validate)
- Session length distribution

### Sync Health
- How many rows are stuck unsynced (offline users, endpoint issues)
- Sync lag across the user base

---

## Source Files

| File | Role |
|------|------|
| `src/skill_lab/core/telemetry.py` | All telemetry logic: config, SQLite, sync, version check |
| `src/skill_lab/core/stats.py` | Query functions for `sklab stats` — reads new tables |
| `src/skill_lab/core/constants.py` | `SKLAB_HOME`, `SKLAB_CONFIG`, `SKLAB_DB` path constants |
| `src/skill_lab/cli.py` | `_with_telemetry` decorator wired into every command; `_record_telemetry` |
| `tests/test_telemetry.py` | Unit tests for all telemetry functions |
| `tests/test_stats.py` | Unit tests for stats queries |
