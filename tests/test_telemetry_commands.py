"""CLI integration tests for `sklab telemetry` subcommands."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from skill_lab.cli import app
from skill_lab.core import telemetry as telemetry_module
from skill_lab.core.telemetry import _write_config, record_event

runner = CliRunner()


@pytest.fixture(autouse=True)
def reset_analytics_cache() -> None:
    """Reset module-level caches before and after every test."""
    telemetry_module._analytics_enabled = None
    telemetry_module._pending_error = None
    telemetry_module._pending_extras.clear()
    yield  # type: ignore[misc]
    telemetry_module._analytics_enabled = None
    telemetry_module._pending_error = None
    telemetry_module._pending_extras.clear()


@pytest.fixture()
def tmp_telemetry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Redirect telemetry I/O to temp directory."""
    home = tmp_path / ".sklab"
    config = home / "config.json"
    db = home / "usage.db"
    monkeypatch.setattr(telemetry_module, "SKLAB_HOME", home)
    monkeypatch.setattr(telemetry_module, "SKLAB_CONFIG", config)
    monkeypatch.setattr(telemetry_module, "SKLAB_DB", db)
    return {"home": home, "config": config, "db": db}


# ─── sklab telemetry enable / disable ────────────────────────────────────────


class TestEnableDisableCommands:
    def test_enable_sets_config(self, tmp_telemetry: dict[str, Path]) -> None:
        result = runner.invoke(app, ["telemetry", "enable"])
        assert result.exit_code == 0
        assert "enabled" in result.output.lower()
        config = json.loads(tmp_telemetry["config"].read_text())
        assert config["analytics_enabled"] is True

    def test_disable_sets_config(self, tmp_telemetry: dict[str, Path]) -> None:
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        result = runner.invoke(app, ["telemetry", "disable"])
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()
        config = json.loads(tmp_telemetry["config"].read_text())
        assert config["analytics_enabled"] is False


# ─── sklab telemetry status ──────────────────────────────────────────────────


class TestStatusCommand:
    def test_status_shows_enabled(
        self, tmp_telemetry: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        result = runner.invoke(app, ["telemetry", "status"])
        assert result.exit_code == 0
        assert "enabled" in result.output.lower()

    def test_status_shows_env_override(
        self, tmp_telemetry: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SKLAB_NO_ANALYTICS", "1")
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        result = runner.invoke(app, ["telemetry", "status"])
        assert result.exit_code == 0
        assert "SKLAB_NO_ANALYTICS" in result.output

    def test_bare_telemetry_shows_status(
        self, tmp_telemetry: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        result = runner.invoke(app, ["telemetry"])
        assert result.exit_code == 0
        assert "Telemetry Status" in result.output


# ─── sklab telemetry purge ───────────────────────────────────────────────────


class TestPurgeCommand:
    def test_purge_deletes_db(
        self, tmp_telemetry: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        record_event("evaluate", 100.0, 0)
        assert tmp_telemetry["db"].exists()

        result = runner.invoke(app, ["telemetry", "purge"], input="y\n")
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()
        assert not tmp_telemetry["db"].exists()

    def test_purge_cancel_noop(
        self, tmp_telemetry: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        record_event("evaluate", 100.0, 0)
        assert tmp_telemetry["db"].exists()

        result = runner.invoke(app, ["telemetry", "purge"], input="n\n")
        # DB should still exist — purge was cancelled
        assert tmp_telemetry["db"].exists()


# ─── sklab telemetry show ────────────────────────────────────────────────────


class TestShowCommand:
    def _seed_events(
        self, tmp_telemetry: dict[str, Path], monkeypatch: pytest.MonkeyPatch, count: int = 3
    ) -> None:
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        for i in range(count):
            record_event(f"cmd-{i}", float(i * 100), 0)

    def test_show_displays_table(
        self, tmp_telemetry: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._seed_events(tmp_telemetry, monkeypatch)
        result = runner.invoke(app, ["telemetry", "show"])
        assert result.exit_code == 0
        assert "Recent Events" in result.output
        assert "cmd-0" in result.output

    def test_show_json_output(
        self, tmp_telemetry: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._seed_events(tmp_telemetry, monkeypatch, count=2)
        result = runner.invoke(app, ["telemetry", "show", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_show_limit_flag(
        self, tmp_telemetry: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._seed_events(tmp_telemetry, monkeypatch, count=5)
        result = runner.invoke(app, ["telemetry", "show", "--json", "-n", "2"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2

    def test_show_empty_db(self, tmp_telemetry: dict[str, Path]) -> None:
        result = runner.invoke(app, ["telemetry", "show"])
        assert result.exit_code == 0
        assert "No events" in result.output
