"""Usage analytics telemetry for sklab.

Collects anonymous command usage data locally (SQLite) and syncs to Supabase.
All telemetry errors are silently swallowed — network failures never crash the CLI.
Telemetry is enabled by default (opt-out); a notice is printed on first run.
Set SKLAB_NO_ANALYTICS=1 to disable telemetry without any prompt.
"""

import contextlib
import json
import os
import platform
import sqlite3
import ssl
import sys
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import certifi

from skill_lab import __version__
from skill_lab.core.constants import SKLAB_CONFIG, SKLAB_DB, SKLAB_HOME

_TELEMETRY_ENDPOINT = "https://api.skill-lab.dev/v1/events"
_RETENTION_DAYS = 90

_FIRST_RUN_NOTICE = (
    "sklab collects anonymous usage data (command names, flags, duration, exit codes, "
    "OS, Python version, skill names, scores, token counts). "
    "No skill content, source paths, or flag values are collected.\n"
    "To opt out: set SKLAB_NO_ANALYTICS=1 or DO_NOT_TRACK=1.\n"
    "Privacy policy: docs/PRIVACY.md"
)

# Module-level cache so we only read config once per process
_analytics_enabled: bool | None = None

# Session UUID: generated once per process, groups commands in one terminal session
_session_uuid: str = str(uuid.uuid4())

# Side-channel for commands to attach extra data to the current telemetry event.
_pending_extras: dict[str, Any] = {}

# Stash for exceptions caught by the decorator, to be recorded after record_event
_pending_error: BaseException | None = None

_CI_PROVIDERS = {
    "GITHUB_ACTIONS": "github_actions",
    "GITLAB_CI": "gitlab_ci",
    "TRAVIS": "travis",
    "CIRCLECI": "circleci",
    "JENKINS_URL": "jenkins",
    "BUILDKITE": "buildkite",
    "TF_BUILD": "azure_pipelines",
    "BITBUCKET_BUILD_NUMBER": "bitbucket",
}


def push_telemetry_extra(**kwargs: Any) -> None:
    """Attach extra data to the next telemetry event recorded by the decorator."""
    _pending_extras.update(kwargs)


def _pop_telemetry_extras() -> dict[str, Any]:
    """Consume and return any pending extra telemetry data."""
    extras = dict(_pending_extras)
    _pending_extras.clear()
    return extras


def _store_pending_error(exc: BaseException) -> None:
    """Stash an exception to be recorded after the next record_event call."""
    global _pending_error
    _pending_error = exc


def _pop_pending_error() -> BaseException | None:
    """Consume and return any pending error."""
    global _pending_error
    err = _pending_error
    _pending_error = None
    return err


def _detect_ci() -> tuple[bool, str | None]:
    """Detect CI environment. Returns (is_ci, provider_name)."""
    for env_var, name in _CI_PROVIDERS.items():
        if os.environ.get(env_var):
            return True, name
    if os.environ.get("CI", "").lower() == "true":
        return True, None
    return False, None


def _ensure_home() -> None:
    SKLAB_HOME.mkdir(parents=True, exist_ok=True)


def _read_config() -> dict[str, Any]:
    if SKLAB_CONFIG.exists():
        try:
            result: dict[str, Any] = json.loads(SKLAB_CONFIG.read_text(encoding="utf-8"))
            return result
        except Exception:
            # Config is corrupt — back it up so the UUID isn't silently lost,
            # then return empty so normal initialization recreates a valid file.
            with contextlib.suppress(Exception):
                SKLAB_CONFIG.rename(SKLAB_CONFIG.with_suffix(".json.bak"))
            return {}
    return {}


def _write_config(config: dict[str, Any]) -> None:
    _ensure_home()
    SKLAB_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _ensure_db() -> None:
    _ensure_home()
    conn = sqlite3.connect(SKLAB_DB)
    with conn:
        # Keep old events table untouched so existing data survives
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_uuid     TEXT    NOT NULL,
                command       TEXT    NOT NULL,
                duration_ms   REAL,
                exit_code     INTEGER,
                sklab_version TEXT,
                platform      TEXT,
                python_version TEXT,
                timestamp     TEXT    NOT NULL,
                synced        INTEGER DEFAULT 0
            )
        """)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        for col, dtype in [
            ("skill_name", "TEXT"),
            ("score", "REAL"),
            ("input_tokens", "INTEGER"),
            ("skill_path", "TEXT"),
        ]:
            if col not in existing:
                conn.execute(f"ALTER TABLE events ADD COLUMN {col} {dtype}")

        # New normalized tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS installs (
                install_uuid   TEXT PRIMARY KEY,
                first_seen_at  TEXT NOT NULL,
                last_seen_at   TEXT NOT NULL,
                run_count      INTEGER NOT NULL DEFAULT 1,
                sklab_version  TEXT,
                os             TEXT,
                python_version TEXT,
                is_ci          INTEGER DEFAULT 0,
                ci_provider    TEXT,
                synced         INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS command_events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                install_uuid  TEXT NOT NULL,
                session_uuid  TEXT NOT NULL,
                sklab_version TEXT,
                command       TEXT NOT NULL,
                subcommand    TEXT,
                flags         TEXT,
                duration_ms   REAL,
                exit_code     INTEGER,
                success       INTEGER,
                is_ci         INTEGER DEFAULT 0,
                ci_provider   TEXT,
                timestamp     TEXT NOT NULL,
                synced        INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_events (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                command_event_id INTEGER,
                install_uuid     TEXT NOT NULL,
                skill_name       TEXT,
                skill_version    TEXT,
                skill_source     TEXT,
                skill_path       TEXT,
                score            REAL,
                model_name       TEXT,
                input_tokens     INTEGER,
                output_tokens    INTEGER,
                step_count       INTEGER,
                tool_call_count  INTEGER,
                execution_time_ms REAL,
                success          INTEGER,
                timestamp        TEXT NOT NULL,
                synced           INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_events (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                command_event_id INTEGER,
                install_uuid     TEXT NOT NULL,
                error_type       TEXT,
                error_module     TEXT,
                command          TEXT,
                sklab_version    TEXT,
                timestamp        TEXT NOT NULL,
                synced           INTEGER DEFAULT 0
            )
        """)
    conn.close()


def init_telemetry() -> bool:
    """Return True if analytics is enabled. Print a notice on first run.

    Telemetry is enabled by default (opt-out model).
    Returns False immediately if any opt-out signal is present:
      - SKLAB_NO_ANALYTICS=1 env var
      - DO_NOT_TRACK=1 env var (consoledonottrack.com standard)
      - CI environment detected (GITHUB_ACTIONS, GITLAB_CI, CI, etc.)
      - Non-interactive stdin (piped input, cron) on first run
    Caches the result for the lifetime of the process.
    """
    global _analytics_enabled

    if _analytics_enabled is not None:
        return _analytics_enabled

    # Env var overrides — disable without any prompt
    if os.environ.get("SKLAB_NO_ANALYTICS", "").strip() == "1":
        _analytics_enabled = False
        return False

    if os.environ.get("DO_NOT_TRACK", "").strip() == "1":
        _analytics_enabled = False
        return False

    # CI environments — disable silently (GitHub Actions, GitLab CI, etc.)
    is_ci, _ = _detect_ci()
    if is_ci:
        _analytics_enabled = False
        return False

    config = _read_config()

    if "analytics_enabled" not in config:
        # Non-interactive context (CI, piped input, cron jobs) — disable silently.
        # Do NOT write config so the next interactive run still shows the notice.
        if not sys.stdout.isatty():
            _analytics_enabled = False
            return False

        # First interactive run — enable by default and print a notice (opt-out model)
        try:
            import typer

            typer.echo(_FIRST_RUN_NOTICE)
        except Exception:
            print(_FIRST_RUN_NOTICE)  # noqa: T201

        config["analytics_enabled"] = True
        config["user_uuid"] = str(uuid.uuid4())
        _write_config(config)

    _analytics_enabled = bool(config.get("analytics_enabled", True))
    return _analytics_enabled


def _upsert_install(
    conn: sqlite3.Connection,
    install_uuid: str,
    timestamp: str,
    is_ci: bool,
    ci_provider: str | None,
) -> None:
    """Insert or update the installs row for this install UUID."""
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    conn.execute(
        """
        INSERT INTO installs (install_uuid, first_seen_at, last_seen_at, run_count,
                              sklab_version, os, python_version, is_ci, ci_provider, synced)
        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(install_uuid) DO UPDATE SET
            last_seen_at   = excluded.last_seen_at,
            run_count      = run_count + 1,
            sklab_version  = excluded.sklab_version,
            is_ci          = excluded.is_ci,
            ci_provider    = excluded.ci_provider,
            synced         = 0
        """,
        (
            install_uuid,
            timestamp,
            timestamp,
            __version__,
            platform.system(),
            py_version,
            int(is_ci),
            ci_provider,
        ),
    )


def record_event(
    command: str,
    duration_ms: float,
    exit_code: int,
    flags: list[str] | None = None,
    skill_name: str | None = None,
    skill_version: str | None = None,
    skill_source: str | None = None,
    skill_path: str | None = None,
    score: float | None = None,
    model_name: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    step_count: int | None = None,
    tool_call_count: int | None = None,
) -> int | None:
    """Write an event to local SQLite, then attempt a fire-and-forget Supabase sync.

    Returns the command_event_id (for use with record_error), or None on failure.
    """
    try:
        if not init_telemetry():
            return None

        config = _read_config()
        install_uuid = config.get("user_uuid") or str(uuid.uuid4())

        _ensure_db()

        timestamp = datetime.now(timezone.utc).isoformat()
        is_ci, ci_provider = _detect_ci()

        with sqlite3.connect(SKLAB_DB) as conn:
            _upsert_install(conn, install_uuid, timestamp, is_ci, ci_provider)

            flags_json = json.dumps(flags) if flags else None
            conn.execute(
                """
                INSERT INTO command_events
                    (install_uuid, session_uuid, sklab_version, command,
                     flags, duration_ms, exit_code, success,
                     is_ci, ci_provider, timestamp, synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    install_uuid,
                    _session_uuid,
                    __version__,
                    command,
                    flags_json,
                    duration_ms,
                    exit_code,
                    int(exit_code == 0),
                    int(is_ci),
                    ci_provider,
                    timestamp,
                ),
            )
            command_event_id: int = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Write skill_events row if any skill field is present
            has_skill_data = any(
                v is not None
                for v in (
                    skill_name,
                    skill_version,
                    skill_source,
                    skill_path,
                    score,
                    model_name,
                    input_tokens,
                    output_tokens,
                    step_count,
                    tool_call_count,
                )
            )
            if has_skill_data:
                conn.execute(
                    """
                    INSERT INTO skill_events
                        (command_event_id, install_uuid, skill_name, skill_version,
                         skill_source, skill_path, score, model_name,
                         input_tokens, output_tokens, step_count, tool_call_count,
                         execution_time_ms, success, timestamp, synced)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        command_event_id,
                        install_uuid,
                        skill_name,
                        skill_version,
                        skill_source,
                        skill_path,
                        score,
                        model_name,
                        input_tokens,
                        output_tokens,
                        step_count,
                        tool_call_count,
                        duration_ms,
                        int(exit_code == 0),
                        timestamp,
                    ),
                )
        conn.close()  # Release file lock on Windows

        _maybe_cleanup()

        # Inline sync: build flat payload from in-memory args, POST immediately
        payload = _build_event_payload(
            install_uuid=install_uuid,
            command=command,
            duration_ms=duration_ms,
            exit_code=exit_code,
            timestamp=timestamp,
            is_ci=is_ci,
            ci_provider=ci_provider,
            flags=flags,
            skill_name=skill_name,
            score=score,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            step_count=step_count,
            tool_call_count=tool_call_count,
        )
        _inline_sync(payload, command_event_id, has_skill_data)

        _sync_to_endpoint()
        return command_event_id

    except Exception:
        return None  # Never let telemetry crash the CLI


def record_error(
    exc: BaseException,
    command: str,
    command_event_id: int | None = None,
) -> None:
    """Record an exception to the error_events table."""
    try:
        if not _analytics_enabled:
            return

        config = _read_config()
        install_uuid = config.get("user_uuid") or ""
        if not install_uuid:
            return

        error_type = type(exc).__name__
        error_module = type(exc).__module__
        timestamp = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(SKLAB_DB) as conn:
            conn.execute(
                """
                INSERT INTO error_events
                    (command_event_id, install_uuid, error_type, error_module,
                     command, sklab_version, timestamp, synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    command_event_id,
                    install_uuid,
                    error_type,
                    error_module,
                    command,
                    __version__,
                    timestamp,
                ),
            )
            error_id: int = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()  # Release file lock on Windows

        # Inline sync for error event
        error_payload: dict[str, Any] = {
            "event_kind": "error",
            "install_uuid": install_uuid,
            "command_event_id": command_event_id,
            "error_type": error_type,
            "error_module": error_module,
            "command": command,
            "sklab_version": __version__,
            "timestamp": timestamp,
        }
        if _post_event(error_payload):
            with contextlib.suppress(Exception), sqlite3.connect(SKLAB_DB) as conn:
                conn.execute(
                    "UPDATE error_events SET synced = 1 WHERE id = ?",
                    (error_id,),
                )

    except Exception:
        pass  # Never let telemetry crash the CLI


def check_for_update() -> str | None:
    """Return the latest PyPI version string if it's newer than the installed version, else None.

    Checks at most once per day; result is cached in config.json.
    Always silently returns None on any error.
    """
    try:
        from datetime import date

        config = _read_config()
        last_check = config.get("last_version_check", "")

        if last_check:
            try:
                last_date = date.fromisoformat(last_check[:10])
                if last_date >= date.today():
                    # Already checked today — use cached result
                    cached = config.get("latest_version", "")
                    return cached if _is_newer(cached, __version__) else None
            except Exception:
                pass  # Bad cache entry — fall through and re-check

        req = urllib.request.Request(
            "https://pypi.org/pypi/skill-lab/json",
            headers={"User-Agent": f"sklab/{__version__}"},
        )
        ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(req, timeout=2, context=ctx) as resp:
            data = json.loads(resp.read())
        latest = data["info"]["version"]

        config["last_version_check"] = datetime.now(timezone.utc).isoformat()
        config["latest_version"] = latest
        _write_config(config)

        return latest if _is_newer(latest, __version__) else None

    except Exception:
        return None


def _is_newer(latest: str, current: str) -> bool:
    """Return True if latest is a strictly higher semver than current."""
    try:
        return tuple(int(x) for x in latest.split(".")) > tuple(int(x) for x in current.split("."))
    except Exception:
        return False


def _build_event_payload(
    install_uuid: str,
    command: str,
    duration_ms: float,
    exit_code: int,
    timestamp: str,
    is_ci: bool,
    ci_provider: str | None,
    flags: list[str] | None = None,
    skill_name: str | None = None,
    score: float | None = None,
    model_name: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    step_count: int | None = None,
    tool_call_count: int | None = None,
) -> dict[str, Any]:
    """Build a flat event payload from in-memory args (no DB query).

    Excludes sensitive fields (skill_path, skill_version, skill_source).
    """
    return {
        "event_kind": "command",
        "install_uuid": install_uuid,
        "session_uuid": _session_uuid,
        "sklab_version": __version__,
        "os": platform.system(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "is_ci": is_ci,
        "ci_provider": ci_provider,
        "command": command,
        "flags": flags or [],
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "timestamp": timestamp,
        "skill_name": skill_name,
        "skill_count": 1 if score is not None else None,
        "total_score": score,
        "mean_score": score,
        "max_score": score,
        "min_score": score,
        "model_name": model_name,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "step_count": step_count,
        "tool_call_count": tool_call_count,
    }


def _post_event(payload: dict[str, Any]) -> bool:
    """POST a single flat JSON payload to the telemetry endpoint.

    Returns True on success.
    Set SKLAB_TELEMETRY_DEBUG=1 to print payload to stderr and return True (no POST).
    """
    try:
        if os.environ.get("SKLAB_TELEMETRY_DEBUG", "").strip() == "1":
            print(json.dumps(payload, indent=2), file=sys.stderr)  # noqa: T201
            return True
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            _TELEMETRY_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(req, timeout=2, context=ctx):
            return True
    except Exception:
        return False


def _inline_sync(
    payload: dict[str, Any],
    command_event_id: int,
    has_skill_event: bool,
) -> None:
    """POST event inline and mark DB rows synced on success only.

    Uses an optimistic claim (synced=2) to prevent duplicate POSTs if
    the retry thread picks up the same event concurrently.
    """
    with contextlib.suppress(Exception), sqlite3.connect(SKLAB_DB) as conn:
        conn.execute(
            "UPDATE command_events SET synced = 2 WHERE id = ? AND synced = 0",
            (command_event_id,),
        )
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            return  # Already claimed by another thread

    if _post_event(payload):
        with contextlib.suppress(Exception), sqlite3.connect(SKLAB_DB) as conn:
            conn.execute(
                "UPDATE command_events SET synced = 1 WHERE id = ?",
                (command_event_id,),
            )
            if has_skill_event:
                conn.execute(
                    "UPDATE skill_events SET synced = 1 WHERE command_event_id = ?",
                    (command_event_id,),
                )
    else:
        # Revert claim so retry thread can pick it up later
        with contextlib.suppress(Exception), sqlite3.connect(SKLAB_DB) as conn:
            conn.execute(
                "UPDATE command_events SET synced = 0 WHERE id = ?",
                (command_event_id,),
            )


def _sync_to_endpoint() -> None:
    """Spawn a daemon thread to retry stale unsynced events. Returns immediately."""
    t = threading.Thread(target=_retry_stale_events, daemon=True)
    t.start()


def _retry_stale_events() -> None:
    """Retry syncing stale unsynced events (older than 1 hour).

    Called in a daemon thread by _sync_to_endpoint(). POSTs each event
    individually via _post_event() and marks synced=1 only on success.
    Uses an optimistic claim (synced=2) to prevent duplicate POSTs from
    concurrent retry threads.
    """
    try:
        if not _analytics_enabled:
            return

        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        with sqlite3.connect(SKLAB_DB) as conn:
            # Retry stale command events (LEFT JOIN for skill + install data)
            stale_cmds = conn.execute(
                """
                SELECT c.id, c.install_uuid, c.session_uuid, c.sklab_version,
                       c.command, c.flags, c.duration_ms, c.exit_code,
                       c.is_ci, c.ci_provider, c.timestamp,
                       s.skill_name, s.score, s.model_name,
                       s.input_tokens, s.output_tokens,
                       s.step_count, s.tool_call_count,
                       i.os, i.python_version
                FROM command_events c
                LEFT JOIN skill_events s ON s.command_event_id = c.id
                LEFT JOIN installs i ON i.install_uuid = c.install_uuid
                WHERE c.synced = 0 AND c.timestamp < ?
                LIMIT 10
                """,
                (cutoff,),
            ).fetchall()

            for row in stale_cmds:
                cmd_id = row[0]
                # Optimistic claim: mark in-flight (synced=2) atomically
                conn.execute(
                    "UPDATE command_events SET synced = 2 WHERE id = ? AND synced = 0",
                    (cmd_id,),
                )
                if conn.execute("SELECT changes()").fetchone()[0] == 0:
                    continue  # Another thread already claimed this event

                score_val = row[12]
                payload: dict[str, Any] = {
                    "event_kind": "command",
                    "install_uuid": row[1],
                    "session_uuid": row[2],
                    "sklab_version": row[3],
                    "os": row[18],
                    "python_version": row[19],
                    "is_ci": bool(row[8]),
                    "ci_provider": row[9],
                    "command": row[4],
                    "flags": json.loads(row[5]) if row[5] else [],
                    "duration_ms": row[6],
                    "exit_code": row[7],
                    "timestamp": row[10],
                    "skill_name": row[11],
                    "skill_count": 1 if score_val is not None else None,
                    "total_score": score_val,
                    "mean_score": score_val,
                    "max_score": score_val,
                    "min_score": score_val,
                    "model_name": row[13],
                    "input_tokens": row[14],
                    "output_tokens": row[15],
                    "step_count": row[16],
                    "tool_call_count": row[17],
                }
                if _post_event(payload):
                    conn.execute(
                        "UPDATE command_events SET synced = 1 WHERE id = ?",
                        (cmd_id,),
                    )
                    conn.execute(
                        "UPDATE skill_events SET synced = 1 WHERE command_event_id = ?",
                        (cmd_id,),
                    )
                else:
                    # Revert claim so another retry can pick it up
                    conn.execute(
                        "UPDATE command_events SET synced = 0 WHERE id = ?",
                        (cmd_id,),
                    )

            # Retry stale error events
            stale_errors = conn.execute(
                """
                SELECT id, install_uuid, command_event_id, error_type,
                       error_module, command, sklab_version, timestamp
                FROM error_events
                WHERE synced = 0 AND timestamp < ?
                LIMIT 10
                """,
                (cutoff,),
            ).fetchall()

            for row in stale_errors:
                err_id = row[0]
                # Optimistic claim
                conn.execute(
                    "UPDATE error_events SET synced = 2 WHERE id = ? AND synced = 0",
                    (err_id,),
                )
                if conn.execute("SELECT changes()").fetchone()[0] == 0:
                    continue

                err_payload: dict[str, Any] = {
                    "event_kind": "error",
                    "install_uuid": row[1],
                    "command_event_id": row[2],
                    "error_type": row[3],
                    "error_module": row[4],
                    "command": row[5],
                    "sklab_version": row[6],
                    "timestamp": row[7],
                }
                if _post_event(err_payload):
                    conn.execute(
                        "UPDATE error_events SET synced = 1 WHERE id = ?",
                        (err_id,),
                    )
                else:
                    conn.execute(
                        "UPDATE error_events SET synced = 0 WHERE id = ?",
                        (err_id,),
                    )
        conn.close()

    except Exception:
        pass  # DB unavailable — silently skip


# ─── Retention / Cleanup ─────────────────────────────────────────────────────


def cleanup_old_data() -> int:
    """Delete rows older than _RETENTION_DAYS from all tables. Returns count deleted."""
    if not SKLAB_DB.exists():
        return 0
    try:
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)).isoformat()
        total = 0
        with sqlite3.connect(SKLAB_DB) as conn:
            for table, ts_col in [
                ("events", "timestamp"),
                ("installs", "last_seen_at"),
                ("command_events", "timestamp"),
                ("skill_events", "timestamp"),
                ("error_events", "timestamp"),
            ]:
                # Table may not exist if DB is from an older version
                with contextlib.suppress(sqlite3.OperationalError):
                    cur = conn.execute(
                        f"DELETE FROM {table} WHERE {ts_col} < ?",
                        (cutoff,),  # noqa: S608
                    )
                    total += cur.rowcount
        conn.close()
        return total
    except Exception:
        return 0


def _maybe_cleanup() -> None:
    """Run cleanup_old_data at most once per day, throttled via config.json."""
    try:
        from datetime import date

        config = _read_config()
        last_cleanup = config.get("last_cleanup", "")
        if last_cleanup:
            try:
                last_date = date.fromisoformat(last_cleanup[:10])
                if last_date >= date.today():
                    return
            except Exception:
                pass
        cleanup_old_data()
        config["last_cleanup"] = datetime.now(timezone.utc).isoformat()
        _write_config(config)
    except Exception:
        pass


# ─── Public API for `sklab telemetry` commands ───────────────────────────────


def enable_telemetry() -> None:
    """Enable telemetry and persist to config."""
    global _analytics_enabled
    config = _read_config()
    config["analytics_enabled"] = True
    if "user_uuid" not in config:
        config["user_uuid"] = str(uuid.uuid4())
    _write_config(config)
    _analytics_enabled = True


def disable_telemetry() -> None:
    """Disable telemetry and persist to config."""
    global _analytics_enabled
    config = _read_config()
    config["analytics_enabled"] = False
    _write_config(config)
    _analytics_enabled = False


def get_telemetry_status() -> dict[str, Any]:
    """Return telemetry status: enabled state, env overrides, row counts, paths."""
    config = _read_config()
    enabled = bool(config.get("analytics_enabled", False))

    env_override: str | None = None
    if os.environ.get("SKLAB_NO_ANALYTICS", "").strip() == "1":
        env_override = "SKLAB_NO_ANALYTICS=1"
        enabled = False
    elif os.environ.get("DO_NOT_TRACK", "").strip() == "1":
        env_override = "DO_NOT_TRACK=1"
        enabled = False

    row_counts: dict[str, int] = {}
    db_size_bytes = 0
    if SKLAB_DB.exists():
        db_size_bytes = SKLAB_DB.stat().st_size
        try:
            with sqlite3.connect(SKLAB_DB) as conn:
                for table in ("installs", "command_events", "skill_events", "error_events"):
                    with contextlib.suppress(sqlite3.OperationalError):
                        count: int = conn.execute(
                            f"SELECT COUNT(*) FROM {table}"  # noqa: S608
                        ).fetchone()[0]
                        row_counts[table] = count
            conn.close()
        except Exception:
            pass

    return {
        "enabled": enabled,
        "env_override": env_override,
        "db_path": str(SKLAB_DB),
        "db_exists": SKLAB_DB.exists(),
        "db_size_bytes": db_size_bytes,
        "row_counts": row_counts,
    }


@dataclass(frozen=True)
class TelemetryEvent:
    """A single telemetry event for display."""

    timestamp: str
    command: str
    duration_ms: float | None
    skill_name: str | None
    score: float | None
    synced: bool


def get_recent_events(limit: int = 20) -> list[TelemetryEvent]:
    """Return recent events by LEFT JOINing command_events with skill_events."""
    if not SKLAB_DB.exists():
        return []
    try:
        with sqlite3.connect(SKLAB_DB) as conn:
            rows = conn.execute(
                """
                SELECT c.timestamp, c.command, c.duration_ms,
                       s.skill_name, s.score, c.synced
                FROM command_events c
                LEFT JOIN skill_events s ON s.command_event_id = c.id
                ORDER BY c.timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        conn.close()
        return [
            TelemetryEvent(
                timestamp=r[0],
                command=r[1],
                duration_ms=r[2],
                skill_name=r[3],
                score=r[4],
                synced=bool(r[5]),
            )
            for r in rows
        ]
    except Exception:
        return []
