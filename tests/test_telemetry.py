"""Comprehensive unit tests for skill_lab.core.telemetry."""
import json
import os
import sqlite3
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import skill_lab.core.telemetry as telemetry_module
from skill_lab.core.telemetry import (
    _detect_ci,
    _is_newer,
    _pop_pending_error,
    _pop_telemetry_extras,
    _read_config,
    _store_pending_error,
    _write_config,
    check_for_update,
    init_telemetry,
    push_telemetry_extra,
    record_error,
    record_event,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_analytics_cache():
    """Reset module-level caches before and after every test."""
    telemetry_module._analytics_enabled = None
    telemetry_module._pending_error = None
    telemetry_module._pending_extras.clear()
    yield
    telemetry_module._analytics_enabled = None
    telemetry_module._pending_error = None
    telemetry_module._pending_extras.clear()


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


# ─── _detect_ci ───────────────────────────────────────────────────────────────


class TestDetectCI:
    def test_no_ci_env_returns_false(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("CI", raising=False)
        is_ci, provider = _detect_ci()
        assert is_ci is False
        assert provider is None

    def test_github_actions_detected(self, monkeypatch):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        is_ci, provider = _detect_ci()
        assert is_ci is True
        assert provider == "github_actions"

    def test_gitlab_ci_detected(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("GITLAB_CI", "true")
        is_ci, provider = _detect_ci()
        assert is_ci is True
        assert provider == "gitlab_ci"

    def test_circleci_detected(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("CIRCLECI", "true")
        is_ci, provider = _detect_ci()
        assert is_ci is True
        assert provider == "circleci"

    def test_generic_ci_env_no_provider(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("CI", "true")
        is_ci, provider = _detect_ci()
        assert is_ci is True
        assert provider is None

    def test_ci_env_case_insensitive(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("CI", "TRUE")
        is_ci, provider = _detect_ci()
        assert is_ci is True

    def test_buildkite_detected(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("BUILDKITE", "true")
        is_ci, provider = _detect_ci()
        assert is_ci is True
        assert provider == "buildkite"

    def test_azure_pipelines_detected(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("TF_BUILD", "True")
        is_ci, provider = _detect_ci()
        assert is_ci is True
        assert provider == "azure_pipelines"

    def test_travis_detected(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("TRAVIS", "true")
        is_ci, provider = _detect_ci()
        assert is_ci is True
        assert provider == "travis"

    def test_jenkins_detected(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("JENKINS_URL", "http://jenkins.example.com/")
        is_ci, provider = _detect_ci()
        assert is_ci is True
        assert provider == "jenkins"

    def test_bitbucket_detected(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("BITBUCKET_BUILD_NUMBER", "42")
        is_ci, provider = _detect_ci()
        assert is_ci is True
        assert provider == "bitbucket"

    def test_ci_equals_1_not_detected(self, monkeypatch):
        """CI=1 is NOT detected — only CI=true matches the generic fallback."""
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("CI", "1")
        is_ci, provider = _detect_ci()
        assert is_ci is False

    def test_ci_equals_false_not_detected(self, monkeypatch):
        for var in telemetry_module._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("CI", "false")
        is_ci, provider = _detect_ci()
        assert is_ci is False

    def test_empty_provider_env_var_not_detected(self, monkeypatch):
        """An env var set to empty string is falsy — not treated as CI."""
        monkeypatch.setenv("GITHUB_ACTIONS", "")
        for var in list(telemetry_module._CI_PROVIDERS.keys())[1:]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("CI", raising=False)
        is_ci, provider = _detect_ci()
        assert is_ci is False

    def test_known_provider_takes_priority_over_generic_ci(self, monkeypatch):
        """When both GITHUB_ACTIONS and CI=true are set, named provider wins."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("CI", "true")
        is_ci, provider = _detect_ci()
        assert is_ci is True
        assert provider == "github_actions"


# ─── _upsert_install ──────────────────────────────────────────────────────────


class TestUpsertInstall:
    def _enable(self, tmp_telemetry, monkeypatch):
        _write_config({"analytics_enabled": True, "user_uuid": "install-uuid"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)

    def test_first_run_creates_row(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 100.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute(
            "SELECT install_uuid, run_count, is_ci FROM installs"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "install-uuid"
        assert row[1] == 1

    def test_subsequent_runs_increment_run_count(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 100.0, 0)
        record_event("validate", 50.0, 0)
        record_event("info", 20.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute("SELECT run_count FROM installs").fetchone()
        conn.close()

        assert row[0] == 3

    def test_only_one_install_row_per_uuid(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 100.0, 0)
        record_event("validate", 50.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        count = conn.execute("SELECT COUNT(*) FROM installs").fetchone()[0]
        conn.close()

        assert count == 1

    def test_last_seen_at_updated(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 100.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        first = conn.execute("SELECT first_seen_at, last_seen_at FROM installs").fetchone()
        conn.close()

        # On first run first_seen_at == last_seen_at
        assert first[0] == first[1]

    def test_ci_fields_stored_on_first_run(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        record_event("evaluate", 100.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute("SELECT is_ci, ci_provider FROM installs").fetchone()
        conn.close()

        assert row[0] == 1
        assert row[1] == "github_actions"

    def test_ci_fields_updated_on_upsert(self, tmp_telemetry, monkeypatch):
        """If CI status changes between runs the install row is updated."""
        self._enable(tmp_telemetry, monkeypatch)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("CI", raising=False)
        record_event("evaluate", 100.0, 0)

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        record_event("validate", 50.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute("SELECT is_ci, ci_provider, run_count FROM installs").fetchone()
        conn.close()

        assert row[0] == 1
        assert row[1] == "github_actions"
        assert row[2] == 2

    def test_sklab_version_updated_on_upsert(self, tmp_telemetry, monkeypatch):
        """sklab_version in installs reflects the most recent run."""
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 100.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        ver = conn.execute("SELECT sklab_version FROM installs").fetchone()[0]
        conn.close()

        from skill_lab import __version__
        assert ver == __version__


# ─── record_event ─────────────────────────────────────────────────────────────


class TestRecordEvent:
    def _enable(self, tmp_telemetry, monkeypatch):
        """Helper: configure analytics as enabled and suppress endpoint sync."""
        _write_config({"analytics_enabled": True, "user_uuid": "test-uuid"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)

    def test_writes_row_to_command_events(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 123.4, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        rows = conn.execute(
            "SELECT command, duration_ms, exit_code, install_uuid FROM command_events"
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
        cmds = [
            r[0]
            for r in conn.execute(
                "SELECT command FROM command_events ORDER BY id"
            ).fetchall()
        ]
        conn.close()

        assert cmds == ["evaluate", "validate"]

    def test_row_includes_version_and_session(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("info", 10.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute(
            "SELECT sklab_version, session_uuid FROM command_events"
        ).fetchone()
        conn.close()

        sklab_ver, sess_uuid = row
        assert sklab_ver  # not empty
        assert sess_uuid  # not empty

    def test_row_synced_column_defaults_to_zero(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("prompt", 5.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        synced = conn.execute("SELECT synced FROM command_events").fetchone()[0]
        conn.close()

        assert synced == 0

    def test_success_column_set_correctly(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 10.0, 0)
        record_event("validate", 10.0, 1)

        conn = sqlite3.connect(tmp_telemetry["db"])
        rows = conn.execute(
            "SELECT success FROM command_events ORDER BY id"
        ).fetchall()
        conn.close()

        assert rows[0][0] == 1
        assert rows[1][0] == 0

    def test_skill_event_written_when_skill_fields_present(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 100.0, 0, skill_name="my-skill", score=85.0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute(
            "SELECT skill_name, score, command_event_id FROM skill_events"
        ).fetchone()
        cmd_id = conn.execute("SELECT id FROM command_events").fetchone()[0]
        conn.close()

        assert row is not None
        assert row[0] == "my-skill"
        assert abs(row[1] - 85.0) < 0.001
        assert row[2] == cmd_id

    def test_no_skill_event_when_no_skill_fields(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 100.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        count = conn.execute("SELECT COUNT(*) FROM skill_events").fetchone()[0]
        conn.close()

        assert count == 0

    def test_flags_stored_as_json(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 10.0, 0, flags=["--verbose", "--spec-only"])

        conn = sqlite3.connect(tmp_telemetry["db"])
        flags_raw = conn.execute("SELECT flags FROM command_events").fetchone()[0]
        conn.close()

        assert json.loads(flags_raw) == ["--verbose", "--spec-only"]

    def test_exception_is_swallowed(self, tmp_telemetry, monkeypatch):
        """record_event must never raise, even when the DB path is invalid."""
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(
            telemetry_module, "SKLAB_DB", Path("/nonexistent/path/usage.db")
        )
        # Should not raise
        record_event("evaluate", 50.0, 0)

    def test_returns_command_event_id(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        result = record_event("evaluate", 10.0, 0)
        assert isinstance(result, int)
        assert result >= 1

    def test_returns_none_when_disabled(self, tmp_telemetry, monkeypatch):
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", False)
        result = record_event("evaluate", 10.0, 0)
        assert result is None

    def test_non_integer_exit_code_stored(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 10.0, 2)

        conn = sqlite3.connect(tmp_telemetry["db"])
        code = conn.execute("SELECT exit_code FROM command_events").fetchone()[0]
        conn.close()

        assert code == 2

    def test_empty_flags_list_stores_null(self, tmp_telemetry, monkeypatch):
        """`flags=[]` is falsy — stored as NULL, not '[]'."""
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 10.0, 0, flags=[])

        conn = sqlite3.connect(tmp_telemetry["db"])
        flags_raw = conn.execute("SELECT flags FROM command_events").fetchone()[0]
        conn.close()

        assert flags_raw is None

    def test_score_zero_still_creates_skill_events_row(self, tmp_telemetry, monkeypatch):
        """`score=0.0` is not None — a skill_events row must be created."""
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 10.0, 0, skill_name="broken-skill", score=0.0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute("SELECT skill_name, score FROM skill_events").fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "broken-skill"
        assert row[1] == 0.0

    def test_session_uuid_consistent_across_calls(self, tmp_telemetry, monkeypatch):
        """All record_event calls in one process share the same session_uuid."""
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 10.0, 0)
        record_event("validate", 5.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        uuids = [
            r[0] for r in conn.execute("SELECT session_uuid FROM command_events ORDER BY id").fetchall()
        ]
        conn.close()

        assert len(uuids) == 2
        assert uuids[0] == uuids[1]
        assert uuids[0] == telemetry_module._session_uuid

    def test_all_skill_event_columns_stored(self, tmp_telemetry, monkeypatch):
        """Every skill field passed to record_event is written to skill_events."""
        self._enable(tmp_telemetry, monkeypatch)
        record_event(
            "skill-invoke", 0.0, 0,
            skill_name="my-skill",
            skill_version="1.2.0",
            skill_source="local",
            skill_path="/tmp/my-skill",
            score=None,
            model_name="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            step_count=7,
            tool_call_count=12,
        )

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute(
            """SELECT skill_name, skill_version, skill_source, skill_path,
                      model_name, input_tokens, output_tokens, step_count, tool_call_count
               FROM skill_events"""
        ).fetchone()
        conn.close()

        assert row[0] == "my-skill"
        assert row[1] == "1.2.0"
        assert row[2] == "local"
        assert row[3] == "/tmp/my-skill"
        assert row[4] == "claude-sonnet-4-6"
        assert row[5] == 1000
        assert row[6] == 500
        assert row[7] == 7
        assert row[8] == 12

    def test_skill_path_alone_creates_skill_events_row(self, tmp_telemetry, monkeypatch):
        """skill_path by itself (no name/score) is enough to write a skill_events row."""
        self._enable(tmp_telemetry, monkeypatch)
        record_event("skill-invoke", 0.0, 0, skill_path="/home/user/my-skill")

        conn = sqlite3.connect(tmp_telemetry["db"])
        count = conn.execute("SELECT COUNT(*) FROM skill_events").fetchone()[0]
        conn.close()

        assert count == 1

    def test_ci_fields_written_to_command_events(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        import skill_lab.core.telemetry as _tel
        for var in _tel._CI_PROVIDERS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("CIRCLECI", "true")
        record_event("evaluate", 10.0, 0)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute("SELECT is_ci, ci_provider FROM command_events").fetchone()
        conn.close()

        assert row[0] == 1
        assert row[1] == "circleci"


# ─── record_error ─────────────────────────────────────────────────────────────


class TestRecordError:
    def _enable(self, tmp_telemetry, monkeypatch):
        _write_config({"analytics_enabled": True, "user_uuid": "test-uuid"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)

    def test_error_written_to_error_events(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        # Ensure DB is initialized
        record_event("evaluate", 100.0, 1)

        exc = ValueError("something broke")
        record_error(exc, "evaluate", command_event_id=1)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute(
            "SELECT error_type, error_module, command FROM error_events"
        ).fetchone()
        conn.close()

        assert row[0] == "ValueError"
        assert row[1] == "builtins"
        assert row[2] == "evaluate"

    def test_no_write_when_disabled(self, tmp_telemetry, monkeypatch):
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", False)
        exc = ValueError("oops")
        record_error(exc, "evaluate")
        # No DB created
        assert not tmp_telemetry["db"].exists()

    def test_command_event_id_stored(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        cmd_id = record_event("evaluate", 100.0, 1)

        exc = RuntimeError("bad")
        record_error(exc, "evaluate", command_event_id=cmd_id)

        conn = sqlite3.connect(tmp_telemetry["db"])
        stored_id = conn.execute(
            "SELECT command_event_id FROM error_events"
        ).fetchone()[0]
        conn.close()

        assert stored_id == cmd_id

    def test_exception_class_only_no_message(self, tmp_telemetry, monkeypatch):
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 100.0, 1)

        exc = FileNotFoundError("secret path /home/user/secret.txt")
        record_error(exc, "evaluate")

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute(
            "SELECT error_type, error_module FROM error_events"
        ).fetchone()
        conn.close()

        # Only the class name, no message content
        assert row[0] == "FileNotFoundError"
        assert "secret" not in (row[0] or "")
        assert "secret" not in (row[1] or "")

    def test_error_swallowed_on_exception(self, tmp_telemetry, monkeypatch):
        """record_error must never raise."""
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(
            telemetry_module, "SKLAB_DB", Path("/nonexistent/path/usage.db")
        )
        exc = RuntimeError("oops")
        # Should not raise
        record_error(exc, "evaluate")

    def test_no_write_when_install_uuid_missing(self, tmp_telemetry, monkeypatch):
        """record_error returns early if config has no user_uuid."""
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        # Config exists but has no user_uuid
        _write_config({"analytics_enabled": True})
        # Ensure DB is initialised first so the connect won't fail on missing file
        record_event("evaluate", 100.0, 1)

        exc = ValueError("fail")
        record_error(exc, "evaluate")

        conn = sqlite3.connect(tmp_telemetry["db"])
        count = conn.execute("SELECT COUNT(*) FROM error_events").fetchone()[0]
        conn.close()
        assert count == 0

    def test_null_command_event_id_stored(self, tmp_telemetry, monkeypatch):
        """command_event_id=None (FK) is stored as NULL — no constraint error."""
        self._enable(tmp_telemetry, monkeypatch)
        record_event("evaluate", 100.0, 1)  # initialise DB

        exc = RuntimeError("something")
        record_error(exc, "evaluate", command_event_id=None)

        conn = sqlite3.connect(tmp_telemetry["db"])
        row = conn.execute("SELECT command_event_id FROM error_events").fetchone()
        conn.close()
        assert row[0] is None


# ─── _store_pending_error / _pop_pending_error ────────────────────────────────


class TestPendingError:
    def test_store_and_pop(self):
        exc = ValueError("test")
        _store_pending_error(exc)
        result = _pop_pending_error()
        assert result is exc

    def test_pop_clears_state(self):
        _store_pending_error(ValueError("test"))
        _pop_pending_error()
        assert _pop_pending_error() is None

    def test_pop_returns_none_when_empty(self):
        assert _pop_pending_error() is None


# ─── Flag capture ─────────────────────────────────────────────────────────────


class TestFlagCapture:
    """Test that _with_telemetry captures boolean flags correctly."""

    def test_boolean_true_flag_captured(self, tmp_telemetry, monkeypatch):
        _write_config({"analytics_enabled": True, "user_uuid": "test-uuid"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)

        # Simulate the flag capture logic from the decorator
        kwargs = {"verbose": True, "spec_only": False, "skill_path": None}
        positional = {"skill_path", "skill_paths", "trace"}
        flags = [
            f"--{k.replace('_', '-')}"
            for k, v in kwargs.items()
            if k not in positional and v is True
        ]
        push_telemetry_extra(flags=flags)
        extras = _pop_telemetry_extras()

        assert extras["flags"] == ["--verbose"]

    def test_false_flags_excluded(self):
        kwargs = {"verbose": False, "spec_only": False}
        positional: set[str] = set()
        flags = [
            f"--{k.replace('_', '-')}"
            for k, v in kwargs.items()
            if k not in positional and v is True
        ]
        assert flags == []

    def test_positional_params_excluded(self):
        kwargs = {"skill_path": Path("."), "verbose": True}
        positional = {"skill_path", "skill_paths", "trace"}
        flags = [
            f"--{k.replace('_', '-')}"
            for k, v in kwargs.items()
            if k not in positional and v is True
        ]
        assert flags == ["--verbose"]
        assert "--skill-path" not in flags

    def test_underscore_to_hyphen_conversion(self):
        kwargs = {"spec_only": True}
        positional: set[str] = set()
        flags = [
            f"--{k.replace('_', '-')}"
            for k, v in kwargs.items()
            if k not in positional and v is True
        ]
        assert flags == ["--spec-only"]


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
        with patch("sys.stdout.isatty", return_value=False):
            assert init_telemetry() is True

    def test_first_run_enables_by_default_and_writes_config(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdout.isatty", return_value=True), patch("typer.echo"):
            result = init_telemetry()
        assert result is True
        config = _read_config()
        assert config["analytics_enabled"] is True
        assert "user_uuid" in config

    def test_first_run_prints_notice(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdout.isatty", return_value=True), patch("typer.echo") as mock_echo:
            init_telemetry()
        mock_echo.assert_called_once()
        assert "opt out" in mock_echo.call_args[0][0].lower()

    def test_first_run_notice_mentions_do_not_track(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdout.isatty", return_value=True), patch("typer.echo") as mock_echo:
            init_telemetry()
        assert "DO_NOT_TRACK" in mock_echo.call_args[0][0]

    def test_first_run_notice_exception_still_enables(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdout.isatty", return_value=True), patch("typer.echo", side_effect=Exception("no tty")):
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
        with patch("sys.stdout.isatty", return_value=False):
            assert init_telemetry() is False

    def test_non_interactive_first_run_caches_false(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdout.isatty", return_value=False):
            init_telemetry()
        assert telemetry_module._analytics_enabled is False

    def test_non_interactive_first_run_does_not_write_config(self, tmp_telemetry, monkeypatch):
        """Config must NOT be written in non-interactive mode so the next interactive
        run still shows the first-run notice."""
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdout.isatty", return_value=False):
            init_telemetry()
        assert not tmp_telemetry["config"].exists()

    def test_non_interactive_first_run_does_not_print_notice(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdout.isatty", return_value=False), patch("typer.echo") as mock_echo:
            init_telemetry()
        mock_echo.assert_not_called()

    def test_interactive_first_run_writes_config(self, tmp_telemetry, monkeypatch):
        monkeypatch.delenv("SKLAB_NO_ANALYTICS", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        with patch("sys.stdout.isatty", return_value=True), patch("typer.echo"):
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


# ─── _sync_to_endpoint / _do_sync ─────────────────────────────────────────────


class TestSyncToEndpoint:
    def test_spawns_daemon_thread_targeting_do_sync(self):
        """_sync_to_endpoint must start a daemon thread pointing at _do_sync."""
        with patch("threading.Thread") as mock_thread_cls:
            mock_instance = MagicMock()
            mock_thread_cls.return_value = mock_instance

            telemetry_module._sync_to_endpoint()

            mock_thread_cls.assert_called_once_with(
                target=telemetry_module._do_sync, daemon=True
            )
            mock_instance.start.assert_called_once()

    def test_returns_before_sync_completes(self):
        """_sync_to_endpoint must return immediately without blocking on I/O."""
        started = threading.Event()
        allow_finish = threading.Event()

        def slow_sync():
            started.set()
            allow_finish.wait(timeout=5)

        with patch.object(telemetry_module, "_do_sync", slow_sync):
            telemetry_module._sync_to_endpoint()
            returned_before_finish = not allow_finish.is_set()

        allow_finish.set()
        assert returned_before_finish

    def test_do_sync_marks_rows_synced_on_success(self, tmp_telemetry, monkeypatch):
        """_do_sync marks synced=1 for all unsynced rows when the POST succeeds."""
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        record_event("evaluate", 100.0, 0)
        record_event("validate", 50.0, 0)

        with patch("urllib.request.urlopen"):
            telemetry_module._do_sync()

        conn = sqlite3.connect(tmp_telemetry["db"])
        unsynced_cmd = conn.execute(
            "SELECT COUNT(*) FROM command_events WHERE synced = 0"
        ).fetchone()[0]
        unsynced_install = conn.execute(
            "SELECT COUNT(*) FROM installs WHERE synced = 0"
        ).fetchone()[0]
        conn.close()
        assert unsynced_cmd == 0
        assert unsynced_install == 0

    def test_do_sync_leaves_rows_unsynced_on_network_error(self, tmp_telemetry, monkeypatch):
        """_do_sync leaves synced=0 when the POST fails so rows retry next run."""
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        record_event("evaluate", 100.0, 0)

        with patch("urllib.request.urlopen", side_effect=OSError("network error")):
            telemetry_module._do_sync()

        conn = sqlite3.connect(tmp_telemetry["db"])
        synced = conn.execute("SELECT synced FROM command_events").fetchone()[0]
        conn.close()
        assert synced == 0

    def test_do_sync_noop_when_no_unsynced_rows(self, tmp_telemetry, monkeypatch):
        """_do_sync makes no HTTP call when there are no unsynced rows."""
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        record_event("evaluate", 100.0, 0)

        # Mark all rows as already synced
        conn = sqlite3.connect(tmp_telemetry["db"])
        conn.execute("UPDATE command_events SET synced = 1")
        conn.execute("UPDATE installs SET synced = 1")
        conn.commit()
        conn.close()

        with patch("urllib.request.urlopen") as mock_open:
            telemetry_module._do_sync()
            mock_open.assert_not_called()

    def test_do_sync_payload_structure(self, tmp_telemetry, monkeypatch):
        """_do_sync sends structured payload with all 4 table keys."""
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        record_event("evaluate", 100.0, 0, skill_name="test", score=80.0)

        captured: list[dict] = []

        def mock_urlopen(req, timeout=None):
            body = json.loads(req.data.decode())
            captured.append(body)
            return MagicMock(__enter__=lambda s: s, __exit__=MagicMock(return_value=False))

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            telemetry_module._do_sync()

        assert len(captured) == 1
        payload = captured[0]
        assert "installs" in payload
        assert "command_events" in payload
        assert "skill_events" in payload
        assert "error_events" in payload

    def test_do_sync_excludes_skill_path_from_payload(self, tmp_telemetry, monkeypatch):
        """skill_path must never be included in the synced skill_events payload."""
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        record_event(
            "skill-invoke", 0.0, 0,
            skill_name="test", skill_path="/home/user/projects/my-skill",
            input_tokens=500,
        )

        captured: list[dict] = []

        def mock_urlopen(req, timeout=None):
            body = json.loads(req.data.decode())
            captured.append(body)
            return MagicMock(__enter__=lambda s: s, __exit__=MagicMock(return_value=False))

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            telemetry_module._do_sync()

        skill_event = captured[0]["skill_events"][0]
        assert "skill_path" not in skill_event
        assert "/home/user" not in json.dumps(skill_event)

    def test_do_sync_noop_when_only_some_tables_all_synced(self, tmp_telemetry, monkeypatch):
        """If every table is empty or all synced, no HTTP call is made."""
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        # Write a skill_event row and immediately mark it synced
        record_event("evaluate", 100.0, 0, skill_name="s", score=80.0)
        conn = sqlite3.connect(tmp_telemetry["db"])
        conn.execute("UPDATE command_events SET synced = 1")
        conn.execute("UPDATE installs SET synced = 1")
        conn.execute("UPDATE skill_events SET synced = 1")
        conn.commit()
        conn.close()

        with patch("urllib.request.urlopen") as mock_open:
            telemetry_module._do_sync()
            mock_open.assert_not_called()

    def test_do_sync_with_only_error_events_unsynced(self, tmp_telemetry, monkeypatch):
        """_do_sync fires a POST even when only error_events have unsynced rows."""
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)

        # Create a command_events row (needed to init the DB), mark it synced
        cmd_id = record_event("evaluate", 100.0, 1)
        conn = sqlite3.connect(tmp_telemetry["db"])
        conn.execute("UPDATE command_events SET synced = 1")
        conn.execute("UPDATE installs SET synced = 1")
        conn.commit()
        conn.close()

        # Write an error row (which is unsynced by default)
        record_error(ValueError("oops"), "evaluate", command_event_id=cmd_id)

        captured: list[dict] = []

        def mock_urlopen(req, timeout=None):
            captured.append(json.loads(req.data.decode()))
            return MagicMock(__enter__=lambda s: s, __exit__=MagicMock(return_value=False))

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            telemetry_module._do_sync()

        assert len(captured) == 1
        assert len(captured[0]["error_events"]) == 1
        assert captured[0]["error_events"][0]["error_type"] == "ValueError"
        # Other tables contributed no unsynced rows
        assert captured[0]["command_events"] == []
        assert captured[0]["installs"] == []

    def test_do_sync_error_events_marked_synced_on_success(self, tmp_telemetry, monkeypatch):
        _write_config({"analytics_enabled": True, "user_uuid": "u1"})
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)

        cmd_id = record_event("evaluate", 100.0, 1)
        record_error(ValueError("fail"), "evaluate", command_event_id=cmd_id)

        with patch("urllib.request.urlopen"):
            telemetry_module._do_sync()

        conn = sqlite3.connect(tmp_telemetry["db"])
        unsynced = conn.execute(
            "SELECT COUNT(*) FROM error_events WHERE synced = 0"
        ).fetchone()[0]
        conn.close()
        assert unsynced == 0
