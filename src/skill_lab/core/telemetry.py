"""Usage analytics telemetry for sklab.

Collects anonymous command usage data locally (SQLite) and syncs to Supabase.
All telemetry errors are silently swallowed — network failures never crash the CLI.
Telemetry is enabled by default (opt-out); a notice is printed on first run.
Set SKLAB_NO_ANALYTICS=1 to disable telemetry without any prompt.
"""

import json
import os
import platform
import sqlite3
import sys
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from skill_lab import __version__
from skill_lab.core.constants import SKLAB_CONFIG, SKLAB_DB, SKLAB_HOME

_TELEMETRY_ENDPOINT = "https://api.skill-lab.dev/v1/events"

_FIRST_RUN_NOTICE = (
    "sklab collects anonymous usage data (command names, flags, duration, exit codes, "
    "OS, Python version, skill names, scores, token counts). "
    "No skill content, file paths, or flag values are collected.\n"
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
            return {}
    return {}


def _write_config(config: dict[str, Any]) -> None:
    _ensure_home()
    SKLAB_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _ensure_db() -> None:
    _ensure_home()
    with sqlite3.connect(SKLAB_DB) as conn:
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


def init_telemetry() -> bool:
    """Return True if analytics is enabled. Print a notice on first run.

    Telemetry is enabled by default (opt-out model).
    Returns False immediately if any opt-out signal is present:
      - SKLAB_NO_ANALYTICS=1 env var
      - DO_NOT_TRACK=1 env var (consoledonottrack.com standard)
      - Non-interactive stdin (CI, piped input, cron) on first run
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
                for v in (skill_name, skill_version, skill_source, skill_path,
                          score, model_name, input_tokens, output_tokens,
                          step_count, tool_call_count)
            )
            if has_skill_data:
                conn.execute(
                    """
                    INSERT INTO skill_events
                        (command_event_id, install_uuid, skill_name, skill_version,
                         skill_source, skill_path, score, model_name,
                         input_tokens, output_tokens, step_count, tool_call_count,
                         timestamp, synced)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
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
                        timestamp,
                    ),
                )

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
        with urllib.request.urlopen(req, timeout=2) as resp:
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
        return tuple(int(x) for x in latest.split(".")) > tuple(
            int(x) for x in current.split(".")
        )
    except Exception:
        return False


def _sync_to_endpoint() -> None:
    """Spawn a daemon thread to POST unsynced rows. Returns immediately."""
    t = threading.Thread(target=_do_sync, daemon=True)
    t.start()


def _do_sync() -> None:
    """POST all unsynced rows to the telemetry endpoint and mark them synced=1 on success."""
    try:
        with sqlite3.connect(SKLAB_DB) as conn:
            install_rows = conn.execute(
                """
                SELECT install_uuid, first_seen_at, last_seen_at, run_count,
                       sklab_version, os, python_version, is_ci, ci_provider
                FROM installs WHERE synced = 0
                """
            ).fetchall()

            cmd_rows = conn.execute(
                """
                SELECT id, install_uuid, session_uuid, sklab_version, command,
                       subcommand, flags, duration_ms, exit_code, success,
                       is_ci, ci_provider, timestamp
                FROM command_events WHERE synced = 0
                """
            ).fetchall()

            # skill_path excluded — local only, never synced to Supabase
            skill_rows = conn.execute(
                """
                SELECT id, command_event_id, install_uuid, skill_name, skill_version,
                       skill_source, score, model_name, input_tokens, output_tokens,
                       step_count, tool_call_count, execution_time_ms, success, timestamp
                FROM skill_events WHERE synced = 0
                """
            ).fetchall()

            error_rows = conn.execute(
                """
                SELECT id, command_event_id, install_uuid, error_type, error_module,
                       command, sklab_version, timestamp
                FROM error_events WHERE synced = 0
                """
            ).fetchall()

            if not (install_rows or cmd_rows or skill_rows or error_rows):
                return

            payload = {
                "installs": [
                    {
                        "install_uuid": r[0],
                        "first_seen_at": r[1],
                        "last_seen_at": r[2],
                        "run_count": r[3],
                        "sklab_version": r[4],
                        "os": r[5],
                        "python_version": r[6],
                        "is_ci": r[7],
                        "ci_provider": r[8],
                    }
                    for r in install_rows
                ],
                "command_events": [
                    {
                        "id": r[0],
                        "install_uuid": r[1],
                        "session_uuid": r[2],
                        "sklab_version": r[3],
                        "command": r[4],
                        "subcommand": r[5],
                        "flags": r[6],
                        "duration_ms": r[7],
                        "exit_code": r[8],
                        "success": r[9],
                        "is_ci": r[10],
                        "ci_provider": r[11],
                        "timestamp": r[12],
                    }
                    for r in cmd_rows
                ],
                "skill_events": [
                    {
                        "id": r[0],
                        "command_event_id": r[1],
                        "install_uuid": r[2],
                        "skill_name": r[3],
                        "skill_version": r[4],
                        "skill_source": r[5],
                        "score": r[6],
                        "model_name": r[7],
                        "input_tokens": r[8],
                        "output_tokens": r[9],
                        "step_count": r[10],
                        "tool_call_count": r[11],
                        "execution_time_ms": r[12],
                        "success": r[13],
                        "timestamp": r[14],
                    }
                    for r in skill_rows
                ],
                "error_events": [
                    {
                        "id": r[0],
                        "command_event_id": r[1],
                        "install_uuid": r[2],
                        "error_type": r[3],
                        "error_module": r[4],
                        "command": r[5],
                        "sklab_version": r[6],
                        "timestamp": r[7],
                    }
                    for r in error_rows
                ],
            }

            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                _TELEMETRY_ENDPOINT,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)

            # Mark all synced rows
            if install_rows:
                install_uuids = [r[0] for r in install_rows]
                placeholders = ",".join("?" * len(install_uuids))
                conn.execute(
                    f"UPDATE installs SET synced = 1 WHERE install_uuid IN ({placeholders})",
                    install_uuids,
                )
            if cmd_rows:
                cmd_ids = [r[0] for r in cmd_rows]
                placeholders = ",".join("?" * len(cmd_ids))
                conn.execute(
                    f"UPDATE command_events SET synced = 1 WHERE id IN ({placeholders})",
                    cmd_ids,
                )
            if skill_rows:
                skill_ids = [r[0] for r in skill_rows]
                placeholders = ",".join("?" * len(skill_ids))
                conn.execute(
                    f"UPDATE skill_events SET synced = 1 WHERE id IN ({placeholders})",
                    skill_ids,
                )
            if error_rows:
                error_ids = [r[0] for r in error_rows]
                placeholders = ",".join("?" * len(error_ids))
                conn.execute(
                    f"UPDATE error_events SET synced = 1 WHERE id IN ({placeholders})",
                    error_ids,
                )

    except Exception:
        pass  # Offline or endpoint unavailable — rows stay unsynced, retry next run
