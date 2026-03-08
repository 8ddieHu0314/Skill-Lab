# DEV_STATS.md — Usage Analytics & Telemetry

Reference for how sklab collects, stores, and syncs usage data.

---

## Overview

Every sklab command optionally records an event containing timing, exit code, and environment metadata. Data flows:

```
sklab command
     │
     ▼
init_telemetry()          ← first-ever run: shows opt-in prompt
     │
     ▼
[command executes]
     │
     ▼ (finally block)
_record_telemetry()
     ├── record_event()   → write row to ~/.sklab/usage.db (SQLite)
     │                    → _sync_to_endpoint() (fire-and-forget POST)
     └── check_for_update() → fetch pypi.org/pypi/skill-lab/json (once/day)
                           → print nudge to stderr if newer version exists
```

All network calls use a short timeout (2–3 s) and swallow every exception. A network failure, endpoint outage, or PyPI timeout never crashes the CLI or affects command output.

---

## User Consent

### First-run prompt

On the very first command a user runs, `init_telemetry()` shows:

```
sklab would like to collect anonymous usage data. This helps improve the tool
and lets you visualise your own command stats. No skill content or file paths
are collected. Enable analytics? [Y/n]:
```

- **Yes** → `analytics_enabled: true` + a fresh UUID written to `~/.sklab/config.json`
- **No** → `analytics_enabled: false` written; no data ever collected or sent

The prompt only appears once. Subsequent runs read the cached value.

### Opt-out mechanisms

| Method | Effect |
|--------|--------|
| Answer **No** to prompt | `analytics_enabled: false` in config; permanent |
| `SKLAB_NO_ANALYTICS=1` env var | Skips prompt and all telemetry for that process; config unchanged |
| Edit `~/.sklab/config.json` | Set `"analytics_enabled": false` manually |

> **Note:** The PyPI version-update check runs regardless of analytics opt-in — it makes no outbound request with user identity and is standard CLI behaviour.

---

## Config File

**Path:** `~/.sklab/config.json`

```json
{
  "user_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "analytics_enabled": true,
  "last_version_check": "2026-03-04T17:41:30.791951+00:00",
  "latest_version": "0.4.0"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `user_uuid` | UUID string | Generated once with `uuid.uuid4()` on opt-in. Never linked to a name, email, or machine identity. |
| `analytics_enabled` | boolean | Written at opt-in time; controls whether events are recorded. |
| `last_version_check` | ISO 8601 UTC | Timestamp of last PyPI version fetch. Used to rate-limit checks to once per day. |
| `latest_version` | semver string | Cached result of last PyPI fetch. Compared to `__version__` to decide whether to show a nudge. |

---

## Local SQLite Database

**Path:** `~/.sklab/usage.db`

**Inspect with:**
```bash
sqlite3 ~/.sklab/usage.db "SELECT * FROM events ORDER BY id DESC LIMIT 20;"
```

### Table: `events`

```sql
CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_uuid      TEXT    NOT NULL,
    command        TEXT    NOT NULL,
    duration_ms    REAL,
    exit_code      INTEGER,
    sklab_version  TEXT,
    platform       TEXT,
    python_version TEXT,
    timestamp      TEXT    NOT NULL,
    synced         INTEGER DEFAULT 0
);
```

### Column Reference

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-incrementing internal row identifier |
| `user_uuid` | TEXT | Anonymous UUID from `config.json` |
| `command` | TEXT | CLI command name: `evaluate`, `validate`, `trigger`, `generate`, `info`, `prompt`, `eval-trace` |
| `duration_ms` | REAL | Wall-clock time the command took in milliseconds (`time.perf_counter()` diff × 1000) |
| `exit_code` | INTEGER | `0` = success, `1` = failure/error |
| `sklab_version` | TEXT | Installed sklab version at time of run (e.g. `"0.4.0"`) |
| `platform` | TEXT | OS name from `platform.system()`: `"Darwin"`, `"Linux"`, `"Windows"` |
| `python_version` | TEXT | Python major.minor (e.g. `"3.12"`) |
| `timestamp` | TEXT | ISO 8601 UTC timestamp of when the command ran |
| `synced` | INTEGER | `0` = pending sync to Supabase, `1` = successfully POSTed |

### Useful queries

```bash
# All events newest first
sqlite3 ~/.sklab/usage.db \
  "SELECT id, command, duration_ms, exit_code, sklab_version, synced
   FROM events ORDER BY id DESC LIMIT 20;"

# Commands that failed
sqlite3 ~/.sklab/usage.db \
  "SELECT command, timestamp FROM events WHERE exit_code != 0;"

# Average duration per command
sqlite3 ~/.sklab/usage.db \
  "SELECT command, ROUND(AVG(duration_ms)) AS avg_ms, COUNT(*) AS runs
   FROM events GROUP BY command ORDER BY runs DESC;"

# Unsynced rows (queued for next run)
sqlite3 ~/.sklab/usage.db \
  "SELECT * FROM events WHERE synced = 0;"
```

---

## Supabase

**Project URL:** `https://uvrzuwsdqfxoocrbnciu.supabase.co`

Data is POSTed via a `urllib` REST call — no SDK dependency. The anon key is safe to embed because Row Level Security restricts it to INSERT only; reads require the service key (dashboard only).

### Table: `usage_events`

```sql
CREATE TABLE usage_events (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_uuid      UUID        NOT NULL,
    command        TEXT        NOT NULL,
    duration_ms    FLOAT,
    exit_code      INTEGER,
    sklab_version  TEXT,
    platform       TEXT,
    python_version TEXT,
    timestamp      TIMESTAMPTZ NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
```

### Column Reference

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Supabase-generated primary key (`gen_random_uuid()`) |
| `user_uuid` | UUID | Same anonymous UUID stored in `~/.sklab/config.json` |
| `command` | TEXT | CLI command name |
| `duration_ms` | FLOAT | Command duration in milliseconds |
| `exit_code` | INTEGER | `0` = success, `1` = failure |
| `sklab_version` | TEXT | sklab version string |
| `platform` | TEXT | OS name |
| `python_version` | TEXT | Python major.minor |
| `timestamp` | TIMESTAMPTZ | UTC timestamp from the client machine |
| `created_at` | TIMESTAMPTZ | UTC timestamp when the row was inserted into Supabase |

### Row Level Security policy

```sql
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_insert" ON usage_events FOR INSERT TO anon WITH CHECK (true);
```

- **Anon key** (embedded in CLI): INSERT only. Cannot read, update, or delete rows.
- **Service key** (dashboard / developer only): Full access.

### Dashboard queries

Run in the Supabase SQL editor:

```sql
-- Most recent events
SELECT command, duration_ms, exit_code, sklab_version, platform, timestamp
FROM usage_events
ORDER BY created_at DESC
LIMIT 20;

-- Command breakdown
SELECT command, COUNT(*) AS runs, ROUND(AVG(duration_ms)) AS avg_ms
FROM usage_events
GROUP BY command
ORDER BY runs DESC;

-- Failure rate per command
SELECT
    command,
    COUNT(*) AS total,
    SUM(CASE WHEN exit_code != 0 THEN 1 ELSE 0 END) AS failures,
    ROUND(100.0 * SUM(CASE WHEN exit_code != 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS failure_pct
FROM usage_events
GROUP BY command
ORDER BY failure_pct DESC;

-- Version distribution
SELECT sklab_version, COUNT(*) AS events
FROM usage_events
GROUP BY sklab_version
ORDER BY sklab_version DESC;

-- Unique users (anonymous)
SELECT COUNT(DISTINCT user_uuid) AS unique_users FROM usage_events;

-- Activity over time (daily)
SELECT DATE(timestamp) AS day, COUNT(*) AS events
FROM usage_events
GROUP BY day
ORDER BY day DESC;
```

---

## Sync Behaviour

Events are written to SQLite first (fast, local), then a sync is attempted immediately after. If the sync fails (offline, timeout, endpoint down), the row stays with `synced = 0`. The next time any sklab command runs, `_sync_to_endpoint()` picks up all unsynced rows and batches them into a single POST.

```
Run 1 (online)  → write row → POST to endpoint → synced = 1
Run 2 (offline) → write row → POST fails       → synced = 0
Run 3 (online)  → write row → POST rows 2+3    → both synced = 1
```

---

## Version Update Check

`check_for_update()` in `telemetry.py` fetches `https://pypi.org/pypi/skill-lab/json` and compares `info.version` against the installed `__version__`. Result is cached in `~/.sklab/config.json` for 24 hours so the network is only hit once per day.

If a newer version is available, a one-line nudge is printed to **stderr** after the command completes (so it never corrupts `--json` output):

```
sklab 0.5.0 is available (you have 0.4.0). Run: pip install --upgrade skill-lab
```

This runs regardless of analytics opt-in.

---

## What Is NOT Collected

- Skill names, file paths, or skill content
- System username or hostname
- Full Python version string (only `major.minor`)
- Any argument values passed to commands
- Environment variables

---

## Source Files

| File | Role |
|------|------|
| `src/skill_lab/core/telemetry.py` | All telemetry logic: config, SQLite, Supabase sync, version check |
| `src/skill_lab/core/constants.py` | `SKLAB_HOME`, `SKLAB_CONFIG`, `SKLAB_DB` path constants |
| `src/skill_lab/cli.py` | `init_telemetry()` + `_record_telemetry()` wired into every command |
