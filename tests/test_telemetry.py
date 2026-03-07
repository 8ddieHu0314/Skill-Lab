"""Comprehensive unit tests for skill_lab.core.telemetry."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import skill_lab.core.telemetry as telemetry_module
from skill_lab.core.telemetry import (
    _is_newer,
    _read_config,
    _write_config,
    check_for_update,
    init_telemetry,
    record_event,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_analytics_cache():
    """Reset module-level _analytics_enabled cache before and after every test."""
    telemetry_module._analytics_enabled = None
    yield
    telemetry_module._analytics_enabled = None


@pytest.fixture
def tmp_telemetry(tmp_path, monkeypatch):
    """Redirect all telemetry I/O to a temp directory so real ~/.sklab is never touched."""
    home = tmp_path / ".sklab"
    config = home / "config.json"
    db = home / "usage.db"
    monkeypatch.setattr(telemetry_module, "SKLAB_HOME", home)
    monkeypatch.setattr(telemetry_module, "SKLAB_CONFIG", config)
    monkeypatch.setattr(telemetry_module, "SKLAB_DB", db)
    return {"home": home, "config": config, "db": db}


def _pypi_mock(version: str) -> MagicMock:
    """Return a mock urlopen context manager yielding a fake PyPI JSON response."""
    resp = MagicMock()
    resp.read.return_value = json.dumps({"info": {"version": version}}).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ─── _is_newer ────────────────────────────────────────────────────────────────


class TestIsNewer:
    def test_newer_major(self):
        assert _is_newer("2.0.0", "1.9.9") is True

    def test_newer_minor(self):
        assert _is_newer("0.5.0", "0.4.9") is True

    def test_newer_patch(self):
        assert _is_newer("0.4.1", "0.4.0") is True

    def test_same_version_is_not_newer(self):
        assert _is_newer("1.0.0", "1.0.0") is False

    def test_older_is_not_newer(self):
        assert _is_newer("0.3.0", "0.4.0") is False

    def test_empty_latest_returns_false(self):
        assert _is_newer("", "1.0.0") is False

    def test_empty_current_returns_false(self):
        assert _is_newer("1.0.0", "") is False

    def test_both_empty_returns_false(self):
        assert _is_newer("", "") is False

    def test_non_numeric_returns_false(self):
        assert _is_newer("abc", "1.0.0") is False

    def test_prerelease_tag_returns_false(self):
        # int("0rc1") raises ValueError → falls to except → False
        assert _is_newer("1.0.0rc1", "0.9.0") is False

    def test_two_part_version_not_newer_than_three_part(self):
        # (1, 0) < (1, 0, 0) in Python tuple comparison → False
        assert _is_newer("1.0", "1.0.0") is False

    def test_high_version_numbers(self):
        assert _is_newer("100.0.0", "99.99.99") is True


# ─── _read_config / _write_config ─────────────────────────────────────────────


class TestConfigRoundTrip:
    def test_write_then_read(self, tmp_telemetry):
        data = {"analytics_enabled": True, "user_uuid": "abc-123"}
        _write_config(data)
        assert _read_config() == data

    def test_read_missing_file_returns_empty(self, tmp_telemetry):
        assert _read_config() == {}

    def test_read_corrupt_json_returns_empty(self, tmp_telemetry):
        tmp_telemetry["home"].mkdir(parents=True, exist_ok=True)
        tmp_telemetry["config"].write_text("not-json{{", encoding="utf-8")
        assert _read_config() == {}

    def test_write_creates_home_dir(self, tmp_telemetry):
        assert not tmp_telemetry["home"].exists()
        _write_config({"key": "value"})
        assert tmp_telemetry["home"].is_dir()
        assert tmp_telemetry["config"].exists()

    def test_write_overwrites_existing(self, tmp_telemetry):
        _write_config({"a": 1})
        _write_config({"b": 2})
        assert _read_config() == {"b": 2}

    def test_nested_values_preserved(self, tmp_telemetry):
        data = {"nested": {"x": [1, 2, 3]}, "flag": False}
        _write_config(data)
        assert _read_config() == data


# ─── record_event ─────────────────────────────────────────────────────────────


class TestRecordEvent:
    def _enable(self, tmp_telemetry, monkeypatch):
        """Helper: configure analytics as enabled and suppress Supabase sync."""
        _write_config({"analytics_enabled": True, "user_uuid": "test-uuid"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_supabase", lambda: None)

    def test_writes_row_to_sqlite(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 123.4, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        rows = conn.execute(
            "SELECT command, duration_ms, exit_code, user_uuid FROM events"
        ).fetchall()
        conn.close()

        assert len(rows) == 1
        cmd, dur, code, uid = rows[0]
        assert cmd == "evaluate"
        assert abs(dur - 123.4) < 0.001
        assert code == 0
        assert uid == "test-uuid"

    def test_no_db_write_when_disabled(self, tmp_telemetry, monkeypatch):
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", False)
        record_event("evaluate", 50.0, 0)
        assert not tmp_telemetry["db"].exists()

    def test_multiple_events_accumulate(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 100.0, 0)
        record_event("validate", 200.0, 1)

        conn = sqlite3.connect(tmp_telemetry["db"])
        cmds = [r[0] for r in conn.execute("SELECT command FROM events ORDER BY id").fetchall()]
        conn.close()

        assert cmds == ["evaluate", "validate"]

    def test_row_includes_version_platform_python(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("info", 10.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute(
            "SELECT sklab_version, platform, python_version FROM events"
        ).fetchone()
        conn.close()

        sklab_ver, plat, py_ver = row
        assert sklab_ver  # not empty
        assert plat       # not empty
        assert "." in py_ver  # e.g. "3.11"

    def test_row_synced_column_defaults_to_zero(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("prompt", 5.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        synced = conn.execute("SELECT synced FROM events").fetchone()[0]
        conn.close()

        assert synced == 0

    def test_exception_is_swallowed(self, tmp_telemetry, monkeypatch):
        """record_event must never raise, even when the DB path is invalid."""
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(
            telemetry_module, "SKLAB_DB", Path("/nonexistent/path/usage.db")
        )
        # Should not raise
        record_event("evaluate", 50.0, 0)

    def test_non_integer_exit_code_stored(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 10.0, 2)

        conn = sqlite3.connect(tmp_telemetry["db"])
        code = conn.execute("SELECT exit_code FROM events").fetchone()[0]
        conn.close()

        assert code == 2


# ─── init_telemetry ───────────────────────────────────────────────────────────


class TestInitTelemetry:
    def test_no_analytics_env_returns_false(self, tmp_telemetry, monkeypatch):
        monkeypatch.setenv("SKLAB_NO_ANALYTICS", "1")
        assert init_telemetry() is False

    def test_no_analytics_env_caches_false(self, tmp_telemetry, monkeypatch):
        monkeypatch.setenv("SKLAB_NO_ANALYTICS", "1")
        init_telemetry()
        assert telemetry_module._analytics_enabled is False

    def test_no_analytics_env_with_whitespace(self, tmp_telemetry, monkeypatch):
        monkeypatch.setenv("SKLAB_NO_ANALYTICS", " 1 ")
        assert init_telemetry() is False

    def test_no_analytics_env_value_zero_does_not_block(self, tmp_telemetry, monkeypatch):
        monkeypatch.setenv("SKLAB_NO_ANALYTICS", "0")
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        assert init_telemetry() is True

    def test_cached_true_returned_immediately(self, tmp_telemetry):
        telemetry_module._analytics_enabled = True
        assert init_telemetry() is True

    def test_cached_false_returned_immediately(self, tmp_telemetry):
        telemetry_module._analytics_enabled = False
        assert init_telemetry() is False

    def test_respects_existing_opt_in(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        assert init_telemetry() is True

    def test_respects_existing_opt_out(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        _write_config({"analytics_enabled": False})
        assert init_telemetry() is False

    def test_respects_existing_config_even_in_non_interactive(self, tmp_telemetry, monkeypatch):
        """TTY check only applies on first run — stored config is always respected."""
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        with patch("sys.stdin.isatty", return_value=False):
            assert init_telemetry() is True

    def test_first_run_enables_by_default_and_writes_config(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdin.isatty", return_value=True), patch("typer.echo"):
            result = init_telemetry()
        assert result is True
        config = _read_config()
        assert config["analytics_enabled"] is True
        assert "user_uuid" in config

    def test_first_run_prints_notice(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdin.isatty", return_value=True), patch("typer.echo") as mock_echo:
            init_telemetry()
        mock_echo.assert_called_once()
        assert "opt out" in mock_echo.call_args[0][0].lower()

    def test_first_run_notice_mentions_do_not_track(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdin.isatty", return_value=True), patch("typer.echo") as mock_echo:
            init_telemetry()
        assert "DO_NOT_TRACK" in mock_echo.call_args[0][0]

    def test_first_run_notice_exception_still_enables(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdin.isatty", return_value=True), patch("typer.echo", side_effect=Exception("no tty")):
            result = init_telemetry()
        assert result is True

    # ── DO_NOT_TRACK ──────────────────────────────────────────────────────────

    def test_do_not_track_returns_false(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        assert init_telemetry() is False

    def test_do_not_track_caches_false(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        init_telemetry()
        assert telemetry_module._analytics_enabled is False

    def test_do_not_track_with_whitespace(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.setenv("DO_NOT_TRACK", " 1 ")
        assert init_telemetry() is False

    def test_do_not_track_zero_does_not_block(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.setenv("DO_NOT_TRACK", "0")
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        assert init_telemetry() is True

    def test_do_not_track_takes_precedence_over_stored_opt_in(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        assert init_telemetry() is False

    def test_both_env_vars_set_returns_false(self, tmp_telemetry, monkeypatch):
        monkeypatch.setenv("SKLAB_NO_ANALYTICS", "1")
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        assert init_telemetry() is False

    # ── Non-interactive stdin (TTY check) ─────────────────────────────────────

    def test_non_interactive_first_run_returns_false(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdin.isatty", return_value=False):
            assert init_telemetry() is False

    def test_non_interactive_first_run_caches_false(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdin.isatty", return_value=False):
            init_telemetry()
        assert telemetry_module._analytics_enabled is False

    def test_non_interactive_first_run_does_not_write_config(self, tmp_telemetry, monkeypatch):
        """Config must NOT be written in non-interactive mode so the next interactive
        run still shows the first-run notice."""
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdin.isatty", return_value=False):
            init_telemetry()
        assert not tmp_telemetry["config"].exists()

    def test_non_interactive_first_run_does_not_print_notice(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdin.isatty", return_value=False), patch("typer.echo") as mock_echo:
            init_telemetry()
        mock_echo.assert_not_called()

    def test_interactive_first_run_writes_config(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdin.isatty", return_value=True), patch("typer.echo"):
            init_telemetry()
        assert tmp_telemetry["config"].exists()
        assert _read_config()["analytics_enabled"] is True


# ─── check_for_update ─────────────────────────────────────────────────────────


class TestCheckForUpdate:
    def test_returns_newer_version(self, tmp_telemetry):
        with patch("urllib.request.urlopen", return_value=_pypi_mock("99.0.0")):
            result = check_for_update()
        assert result == "99.0.0"

    def test_returns_none_when_already_latest(self, tmp_telemetry):
        with patch("urllib.request.urlopen", return_value=_pypi_mock("0.0.1")):
            result = check_for_update()
        assert result is None

    def test_caches_after_first_check_no_network_call(self, tmp_telemetry):
        with patch("urllib.request.urlopen", return_value=_pypi_mock("99.0.0")) as mock_open:
            check_for_update()       # first call — hits network
            mock_open.reset_mock()
            result = check_for_update()  # second call — should use cache
            mock_open.assert_not_called()
        assert result == "99.0.0"

    def test_stale_cache_triggers_new_network_call(self, tmp_telemetry):
        _write_config({
            "last_version_check": "2000-01-01T00:00:00+00:00",
            "latest_version": "1.0.0",
        })
        with patch("urllib.request.urlopen", return_value=_pypi_mock("99.0.0")) as mock_open:
            result = check_for_update()
            mock_open.assert_called_once()
        assert result == "99.0.0"

    def test_bad_cache_date_falls_through_to_network(self, tmp_telemetry):
        _write_config({"last_version_check": "not-a-date", "latest_version": "99.0.0"})
        with patch("urllib.request.urlopen", return_value=_pypi_mock("99.0.0")) as mock_open:
            check_for_update()
            mock_open.assert_called_once()

    def test_network_error_returns_none(self, tmp_telemetry):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = check_for_update()
        assert result is None

    def test_writes_latest_version_to_cache(self, tmp_telemetry):
        with patch("urllib.request.urlopen", return_value=_pypi_mock("5.0.0")):
            check_for_update()
        config = _read_config()
        assert config.get("latest_version") == "5.0.0"
        assert "last_version_check" in config

    def test_cached_older_version_returns_none(self, tmp_telemetry):
        """Cache hit where cached version is NOT newer — should return None."""
        from datetime import datetime, timezone

        _write_config({
            "last_version_check": datetime.now(timezone.utc).isoformat(),
            "latest_version": "0.0.1",
        })
        with patch("urllib.request.urlopen") as mock_open:
            result = check_for_update()
            mock_open.assert_not_called()  # served from cache
        assert result is None
