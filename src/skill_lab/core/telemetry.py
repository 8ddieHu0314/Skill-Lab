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
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from skill_lab import __version__
from skill_lab.core.constants import SKLAB_CONFIG, SKLAB_DB, SKLAB_HOME

_TELEMETRY_ENDPOINT = "https://sklab-telemetry.sklab.workers.dev/v1/events"

_FIRST_RUN_NOTICE = (
    "sklab collects anonymous usage data to improve the tool and let you visualise "
    "your own command stats. No skill content or file paths are collected.\n"
    "To opt out: set SKLAB_NO_ANALYTICS=1, DO_NOT_TRACK=1, or run `sklab telemetry off`."
)

# Module-level cache so we only read config once per process
_analytics_enabled: bool | None = None

# Side-channel for commands to attach extra data to the current telemetry event.
# Commands call push_telemetry_extra(); the decorator pops it via _pop_telemetry_extras().
_pending_extras: dict[str, Any] = {}


def push_telemetry_extra(**kwargs: Any) -> None:
    """Attach extra data to the next telemetry event recorded by the decorator."""
    _pending_extras.update(kwargs)


def _pop_telemetry_extras() -> dict[str, Any]:
    """Consume and return any pending extra telemetry data."""
    extras = dict(_pending_extras)
    _pending_extras.clear()
    return extras


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
        # Migrate: add stats columns if they don't exist (idempotent)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        for col, dtype in [
            ("skill_name", "TEXT"),
            ("score", "REAL"),
            ("input_tokens", "INTEGER"),
            ("skill_path", "TEXT"),
        ]:
            if col not in existing:
                conn.execute(f"ALTER TABLE events ADD COLUMN {col} {dtype}")


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
        if not sys.stdin.isatty():
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


def record_event(
    command: str,
    duration_ms: float,
    exit_code: int,
    skill_name: str | None = None,
    score: float | None = None,
    input_tokens: int | None = None,
    skill_path: str | None = None,
) -> None:
    """Write an event to local SQLite, then attempt a fire-and-forget Supabase sync."""
    try:
        if not init_telemetry():
            return

        config = _read_config()
        user_uuid = config.get("user_uuid") or str(uuid.uuid4())

        _ensure_db()

        py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        timestamp = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(SKLAB_DB) as conn:
            conn.execute(
                """
                INSERT INTO events
                    (user_uuid, command, duration_ms, exit_code,
                     sklab_version, platform, python_version, timestamp,
                     skill_name, score, input_tokens, skill_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_uuid,
                    command,
                    duration_ms,
                    exit_code,
                    __version__,
                    platform.system(),
                    py_version,
                    timestamp,
                    skill_name,
                    score,
                    input_tokens,
                    skill_path,
                ),
            )

        _sync_to_supabase()

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


def _sync_to_supabase() -> None:
    """POST all unsynced rows to the telemetry endpoint and mark them synced=1 on success."""
    try:
        with sqlite3.connect(SKLAB_DB) as conn:
            rows = conn.execute(
                """
                SELECT id, user_uuid, command, duration_ms, exit_code,
                       sklab_version, platform, python_version, timestamp
                FROM events WHERE synced = 0
                """
            ).fetchall()

            if not rows:
                return

            payload = [
                {
                    "user_uuid": r[1],
                    "command": r[2],
                    "duration_ms": r[3],
                    "exit_code": r[4],
                    "sklab_version": r[5],
                    "platform": r[6],
                    "python_version": r[7],
                    "timestamp": r[8],
                }
                for r in rows
            ]
            row_ids = [r[0] for r in rows]

            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                _TELEMETRY_ENDPOINT,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)

            # Mark rows as synced
            placeholders = ",".join("?" * len(row_ids))
            conn.execute(
                f"UPDATE events SET synced = 1 WHERE id IN ({placeholders})",
                row_ids,
            )

    except Exception:
        pass  # Offline or endpoint unavailable — rows stay unsynced, retry next run
