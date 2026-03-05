"""Usage analytics telemetry for sklab.

Collects anonymous command usage data locally (SQLite) and syncs to Supabase.
All telemetry errors are silently swallowed — network failures never crash the CLI.
Users opt in on first run via an interactive prompt.
Set SKLAB_NO_ANALYTICS=1 to skip all telemetry without prompting.
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

_SUPABASE_URL = "https://uvrzuwsdqfxoocrbnciu.supabase.co"
_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV2cnp1d3NkcWZ4b29jcmJuY2l1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI1ODIzNTYsImV4cCI6MjA4ODE1ODM1Nn0"
    ".0y5hTH4HVKdYU54kG7bzyFpKnOVPrNMBvffJzNIDfEU"
)

_OPT_IN_PROMPT = (
    "sklab would like to collect anonymous usage data. "
    "This helps improve the tool and lets you visualise your own command stats. "
    "No skill content or file paths are collected. Enable analytics?"
)

# Module-level cache so we only read config once per process
_analytics_enabled: bool | None = None


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
    conn = sqlite3.connect(SKLAB_DB)
    try:
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
        conn.commit()
    finally:
        conn.close()


def init_telemetry() -> bool:
    """Return True if analytics is enabled. Show opt-in prompt on first run.

    Returns False immediately if SKLAB_NO_ANALYTICS=1 is set.
    Caches the result for the lifetime of the process.
    """
    global _analytics_enabled

    if _analytics_enabled is not None:
        return _analytics_enabled

    # Env var override — skip prompt entirely
    if os.environ.get("SKLAB_NO_ANALYTICS", "").strip() == "1":
        _analytics_enabled = False
        return False

    config = _read_config()

    if "analytics_enabled" not in config:
        # First run — show prompt
        try:
            import typer
            enabled = typer.confirm(_OPT_IN_PROMPT, default=True)
        except Exception:
            enabled = False

        config["analytics_enabled"] = enabled
        if enabled:
            config["user_uuid"] = str(uuid.uuid4())
        _write_config(config)

    _analytics_enabled = bool(config.get("analytics_enabled", False))
    return _analytics_enabled


def record_event(command: str, duration_ms: float, exit_code: int) -> None:
    """Write an event to local SQLite, then attempt a fire-and-forget Supabase sync."""
    try:
        if not init_telemetry():
            return

        config = _read_config()
        user_uuid = config.get("user_uuid") or str(uuid.uuid4())

        _ensure_db()

        py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        timestamp = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(SKLAB_DB)
        try:
            conn.execute(
                """
                INSERT INTO events
                    (user_uuid, command, duration_ms, exit_code,
                     sklab_version, platform, python_version, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            conn.commit()
        finally:
            conn.close()

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
    """POST all unsynced rows to Supabase and mark them synced=1 on success."""
    try:
        conn = sqlite3.connect(SKLAB_DB)
        try:
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
                f"{_SUPABASE_URL}/rest/v1/usage_events",
                data=data,
                headers={
                    "apikey": _SUPABASE_ANON_KEY,
                    "Authorization": f"Bearer {_SUPABASE_ANON_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)

            # Mark rows as synced
            placeholders = ",".join("?" * len(row_ids))
            conn.execute(
                f"UPDATE events SET synced = 1 WHERE id IN ({placeholders})",
                row_ids,
            )
            conn.commit()
        finally:
            conn.close()

    except Exception:
        pass  # Offline or Supabase unavailable — rows stay unsynced, retry next run
