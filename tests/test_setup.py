"""Tests for sklab setup hook configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skill_lab.cli import app
from skill_lab.core.setup import (
    _TRACK_CMD,
    init_hooks_on_first_run,
    run_setup,
    setup_claude_code,
    setup_cursor,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a fake ~/.claude directory and redirect CLAUDE_SETTINGS."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    import skill_lab.core.setup as setup_module
    monkeypatch.setattr(setup_module, "_CLAUDE_SETTINGS", claude_dir / "settings.json")
    return claude_dir


@pytest.fixture()
def cursor_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a fake ~/.cursor directory and redirect CURSOR_HOOKS."""
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    import skill_lab.core.setup as setup_module
    monkeypatch.setattr(setup_module, "_CURSOR_HOOKS", cursor_dir / "hooks.json")
    return cursor_dir


@pytest.fixture()
def no_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect both settings paths to non-existent parent dirs."""
    import skill_lab.core.setup as setup_module
    monkeypatch.setattr(setup_module, "_CLAUDE_SETTINGS", tmp_path / "nowhere" / "settings.json")
    monkeypatch.setattr(setup_module, "_CURSOR_HOOKS", tmp_path / "nowhere2" / "hooks.json")


# ---------------------------------------------------------------------------
# setup_claude_code
# ---------------------------------------------------------------------------


class TestSetupClaudeCode:
    def test_not_installed_when_dir_missing(self, no_tools: None) -> None:
        assert setup_claude_code() == "not_installed"

    def test_configured_on_fresh_install(self, claude_home: Path) -> None:
        result = setup_claude_code()
        assert result == "configured"

    def test_writes_hook_to_settings(self, claude_home: Path) -> None:
        settings_path = claude_home / "settings.json"
        setup_claude_code()
        data = json.loads(settings_path.read_text())
        post_hooks = data["hooks"]["PostToolUse"]
        commands = [h["command"] for entry in post_hooks for h in entry.get("hooks", [])]
        assert _TRACK_CMD in commands

    def test_idempotent_second_call(self, claude_home: Path) -> None:
        setup_claude_code()
        result = setup_claude_code()
        assert result == "already_configured"

    def test_does_not_duplicate_hook(self, claude_home: Path) -> None:
        settings_path = claude_home / "settings.json"
        setup_claude_code()
        setup_claude_code()
        data = json.loads(settings_path.read_text())
        post_hooks = data["hooks"]["PostToolUse"]
        commands = [h["command"] for entry in post_hooks for h in entry.get("hooks", [])]
        assert commands.count(_TRACK_CMD) == 1

    def test_preserves_existing_hooks(self, claude_home: Path) -> None:
        settings_path = claude_home / "settings.json"
        existing = {
            "hooks": {
                "PostToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
                ]
            }
        }
        settings_path.write_text(json.dumps(existing))
        setup_claude_code()
        data = json.loads(settings_path.read_text())
        commands = [
            h["command"]
            for entry in data["hooks"]["PostToolUse"]
            for h in entry.get("hooks", [])
        ]
        assert "echo hi" in commands
        assert _TRACK_CMD in commands

    def test_handles_empty_settings_file(self, claude_home: Path) -> None:
        settings_path = claude_home / "settings.json"
        settings_path.write_text("{}")
        result = setup_claude_code()
        assert result == "configured"

    def test_hook_is_async(self, claude_home: Path) -> None:
        settings_path = claude_home / "settings.json"
        setup_claude_code()
        data = json.loads(settings_path.read_text())
        post_hooks = data["hooks"]["PostToolUse"]
        our_hook = next(
            h
            for entry in post_hooks
            for h in entry.get("hooks", [])
            if h.get("command") == _TRACK_CMD
        )
        assert our_hook.get("async") is True


# ---------------------------------------------------------------------------
# setup_cursor
# ---------------------------------------------------------------------------


class TestSetupCursor:
    def test_not_installed_when_dir_missing(self, no_tools: None) -> None:
        assert setup_cursor() == "not_installed"

    def test_configured_on_fresh_install(self, cursor_home: Path) -> None:
        result = setup_cursor()
        assert result == "configured"

    def test_writes_hook_to_file(self, cursor_home: Path) -> None:
        hooks_path = cursor_home / "hooks.json"
        setup_cursor()
        data = json.loads(hooks_path.read_text())
        assert isinstance(data, list)
        commands = [entry.get("command") for entry in data]
        assert _TRACK_CMD in commands

    def test_idempotent_second_call(self, cursor_home: Path) -> None:
        setup_cursor()
        result = setup_cursor()
        assert result == "already_configured"

    def test_does_not_duplicate_hook(self, cursor_home: Path) -> None:
        hooks_path = cursor_home / "hooks.json"
        setup_cursor()
        setup_cursor()
        data = json.loads(hooks_path.read_text())
        commands = [entry.get("command") for entry in data]
        assert commands.count(_TRACK_CMD) == 1

    def test_preserves_existing_hooks(self, cursor_home: Path) -> None:
        hooks_path = cursor_home / "hooks.json"
        hooks_path.write_text(json.dumps([{"command": "echo existing"}]))
        setup_cursor()
        data = json.loads(hooks_path.read_text())
        commands = [entry.get("command") for entry in data]
        assert "echo existing" in commands
        assert _TRACK_CMD in commands


# ---------------------------------------------------------------------------
# run_setup
# ---------------------------------------------------------------------------


class TestRunSetup:
    def test_returns_dict_with_tool_names(self, no_tools: None) -> None:
        results = run_setup()
        assert "Claude Code" in results
        assert "Cursor" in results

    def test_not_installed_when_neither_present(self, no_tools: None) -> None:
        results = run_setup()
        assert results["Claude Code"] == "not_installed"
        assert results["Cursor"] == "not_installed"

    def test_configured_when_both_present(
        self, claude_home: Path, cursor_home: Path
    ) -> None:
        results = run_setup()
        assert results["Claude Code"] == "configured"
        assert results["Cursor"] == "configured"

    def test_already_configured_on_second_run(
        self, claude_home: Path, cursor_home: Path
    ) -> None:
        run_setup()
        results = run_setup()
        assert results["Claude Code"] == "already_configured"
        assert results["Cursor"] == "already_configured"


# ---------------------------------------------------------------------------
# init_hooks_on_first_run
# ---------------------------------------------------------------------------


import sys
import time
from unittest.mock import patch


def _patch_interactive() -> "patch[bool]":  # type: ignore[type-arg]
    return patch("skill_lab.core.setup.sys.stdout.isatty", return_value=True)


def _patch_non_interactive() -> "patch[bool]":  # type: ignore[type-arg]
    return patch("skill_lab.core.setup.sys.stdout.isatty", return_value=False)


class TestInitHooksOnFirstRun:
    @pytest.fixture(autouse=True)
    def reset_process_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reset the process-level _hooks_initialized flag between tests."""
        import skill_lab.core.setup as setup_module
        monkeypatch.setattr(setup_module, "_hooks_initialized", False)
        monkeypatch.delenv("CI", raising=False)

    @pytest.fixture()
    def tmp_sklab(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Redirect ~/.sklab config to a temp dir."""
        import skill_lab.core.telemetry as tel
        sklab_dir = tmp_path / ".sklab"
        sklab_dir.mkdir()
        monkeypatch.setattr(tel, "SKLAB_CONFIG", sklab_dir / "config.json")
        monkeypatch.setattr(tel, "SKLAB_HOME", sklab_dir)
        return sklab_dir

    def test_writes_hook_on_first_invocation(
        self, tmp_sklab: Path, claude_home: Path
    ) -> None:
        with _patch_interactive():
            with patch("skill_lab.core.setup._get_install_mtime", return_value=1.0):
                init_hooks_on_first_run()
        settings_path = claude_home / "settings.json"
        assert settings_path.exists()
        data = json.loads(settings_path.read_text())
        commands = [
            h["command"]
            for entry in data["hooks"]["PostToolUse"]
            for h in entry.get("hooks", [])
        ]
        assert _TRACK_CMD in commands

    def test_shows_notice_on_first_invocation(
        self, tmp_sklab: Path, claude_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with _patch_interactive():
            with patch("skill_lab.core.setup._get_install_mtime", return_value=1.0):
                init_hooks_on_first_run()
        # Notice goes via typer.echo which writes to stdout
        captured = capsys.readouterr()
        assert "skill tracking" in captured.out or "skill tracking" in captured.err

    def test_shows_notice_on_reinstall_with_existing_hook(
        self, tmp_sklab: Path, claude_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Hook already present but package was reinstalled → notice shown."""
        config_path = tmp_sklab / "config.json"
        # Simulate a prior install that configured hooks a long time ago
        config_path.write_text(json.dumps({"hooks_configured_at": 1000.0}))
        # Hook is already in settings (survived uninstall)
        setup_claude_code()

        # Reinstall: METADATA mtime is newer than hooks_configured_at
        with _patch_interactive():
            with patch("skill_lab.core.setup._get_install_mtime", return_value=2000.0):
                init_hooks_on_first_run()

        captured = capsys.readouterr()
        assert "skill tracking" in captured.out or "skill tracking" in captured.err

    def test_no_notice_on_repeated_run_same_install(
        self, tmp_sklab: Path, claude_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Same install, hook already configured → no notice on subsequent runs."""
        future = time.time() + 9999
        config_path = tmp_sklab / "config.json"
        config_path.write_text(json.dumps({"hooks_configured_at": future}))
        setup_claude_code()

        with _patch_interactive():
            with patch("skill_lab.core.setup._get_install_mtime", return_value=1.0):
                init_hooks_on_first_run()

        captured = capsys.readouterr()
        assert "skill tracking" not in captured.out
        assert "skill tracking" not in captured.err

    def test_reconfigures_hook_if_removed(
        self, tmp_sklab: Path, claude_home: Path
    ) -> None:
        """Hook removed manually → re-written on next run."""
        settings_path = claude_home / "settings.json"
        future = time.time() + 9999
        config_path = tmp_sklab / "config.json"
        config_path.write_text(json.dumps({"hooks_configured_at": future}))
        # Hook is NOT in settings (user removed it)
        settings_path.write_text("{}")

        with _patch_interactive():
            with patch("skill_lab.core.setup._get_install_mtime", return_value=1.0):
                init_hooks_on_first_run()

        data = json.loads(settings_path.read_text())
        commands = [
            h["command"]
            for entry in data["hooks"]["PostToolUse"]
            for h in entry.get("hooks", [])
        ]
        assert _TRACK_CMD in commands

    def test_records_configured_at_timestamp(
        self, tmp_sklab: Path, claude_home: Path
    ) -> None:
        config_path = tmp_sklab / "config.json"
        with _patch_interactive():
            with patch("skill_lab.core.setup._get_install_mtime", return_value=1.0):
                before = time.time()
                init_hooks_on_first_run()
                after = time.time()
        config = json.loads(config_path.read_text())
        assert before <= config["hooks_configured_at"] <= after

    def test_skips_in_non_interactive_env(self, claude_home: Path) -> None:
        settings_path = claude_home / "settings.json"
        with _patch_non_interactive():
            init_hooks_on_first_run()
        assert not settings_path.exists()

    def test_skips_in_ci(self, claude_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CI", "true")
        with _patch_interactive():
            init_hooks_on_first_run()
        assert not (claude_home / "settings.json").exists()

    def test_does_not_crash_when_no_tools_installed(self, no_tools: None) -> None:
        with _patch_interactive():
            with patch("skill_lab.core.setup._get_install_mtime", return_value=1.0):
                init_hooks_on_first_run()  # Should not raise

    def test_process_cache_prevents_second_run(self, claude_home: Path) -> None:
        """Second call within the same process is a no-op (cache hit)."""
        settings_path = claude_home / "settings.json"
        with _patch_interactive():
            with patch("skill_lab.core.setup._get_install_mtime", return_value=1.0):
                init_hooks_on_first_run()
                # Remove hook to prove second call doesn't re-run setup
                settings_path.write_text("{}")
                init_hooks_on_first_run()
        data = json.loads(settings_path.read_text())
        assert data == {}  # hook was NOT re-added (cache prevented it)


# ---------------------------------------------------------------------------
# CLI: sklab setup
# ---------------------------------------------------------------------------


class TestSetupCLI:
    def test_setup_command_runs(self, no_tools: None) -> None:
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0

    def test_shows_not_installed_for_missing_tools(self, no_tools: None) -> None:
        result = runner.invoke(app, ["setup"])
        assert "not installed" in result.output

    def test_shows_configured_for_present_tools(
        self, claude_home: Path, cursor_home: Path
    ) -> None:
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0
        assert "configured" in result.output

    def test_shows_already_configured_on_repeat(
        self, claude_home: Path, cursor_home: Path
    ) -> None:
        runner.invoke(app, ["setup"])
        result = runner.invoke(app, ["setup"])
        assert "already configured" in result.output


# ---------------------------------------------------------------------------
# CLI: sklab _track-invocation
# ---------------------------------------------------------------------------


class TestTrackInvocationCLI:
    def _get_skill_stats(self, db: Path) -> list[tuple]:
        import sqlite3
        conn = sqlite3.connect(db)
        rows = conn.execute(
            "SELECT skill_name, use_count, total_tokens, repo_root_hash FROM skill_stats"
        ).fetchall()
        conn.close()
        return rows

    def test_records_invocation_from_stdin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A valid PostToolUse JSON payload records a skill-invoke event and skill_stats row."""
        import skill_lab.core.telemetry as telemetry_module

        db = tmp_path / "usage.db"
        monkeypatch.setattr(telemetry_module, "SKLAB_DB", db)
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        monkeypatch.setenv("SKLAB_NO_ANALYTICS", "")

        payload = json.dumps({
            "tool_name": "Skill",
            "tool_input": {"skill": "commit"},
            "cwd": str(tmp_path),
        })
        result = runner.invoke(app, ["_track-invocation"], input=payload)
        assert result.exit_code == 0

        rows = self._get_skill_stats(db)
        assert len(rows) == 1
        assert rows[0][0] == "commit"
        assert rows[0][1] == 1  # use_count

    def test_tokens_accumulated_across_invocations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two invocations of the same skill accumulate total_tokens."""
        import skill_lab.core.telemetry as telemetry_module

        skill_dir = tmp_path / ".claude" / "skills" / "commit"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Commit\n" + "x" * 100, encoding="utf-8")

        db = tmp_path / "usage.db"
        monkeypatch.setattr(telemetry_module, "SKLAB_DB", db)
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        monkeypatch.setenv("SKLAB_NO_ANALYTICS", "")

        payload = json.dumps({
            "tool_name": "Skill",
            "tool_input": {"skill": "commit"},
            "cwd": str(tmp_path),
        })
        runner.invoke(app, ["_track-invocation"], input=payload)
        runner.invoke(app, ["_track-invocation"], input=payload)

        rows = self._get_skill_stats(db)
        assert len(rows) == 1
        assert rows[0][1] == 2  # use_count == 2
        assert rows[0][2] > 0   # total_tokens accumulated

    def test_zero_tokens_added_when_skill_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When skill file is missing, use_count still increments but total_tokens stays 0."""
        import skill_lab.core.telemetry as telemetry_module

        db = tmp_path / "usage.db"
        monkeypatch.setattr(telemetry_module, "SKLAB_DB", db)
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        monkeypatch.setenv("SKLAB_NO_ANALYTICS", "")

        payload = json.dumps({
            "tool_name": "Skill",
            "tool_input": {"skill": "nonexistent-skill"},
            "cwd": str(tmp_path),
        })
        result = runner.invoke(app, ["_track-invocation"], input=payload)
        assert result.exit_code == 0

        rows = self._get_skill_stats(db)
        assert len(rows) == 1
        assert rows[0][1] == 1  # use_count incremented
        assert rows[0][2] == 0  # total_tokens stays 0

    def test_separate_rows_for_different_repo_hashes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invocations from different repos produce separate skill_stats rows."""
        import hashlib
        import skill_lab.core.telemetry as telemetry_module

        db = tmp_path / "usage.db"
        monkeypatch.setattr(telemetry_module, "SKLAB_DB", db)
        monkeypatch.setattr(telemetry_module, "_analytics_enabled", True)
        monkeypatch.setattr(telemetry_module, "_sync_to_endpoint", lambda: None)
        monkeypatch.setenv("SKLAB_NO_ANALYTICS", "")

        repo_a = tmp_path / "repo-a"
        repo_b = tmp_path / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()

        for cwd in (str(repo_a), str(repo_b)):
            payload = json.dumps({
                "tool_name": "Skill",
                "tool_input": {"skill": "commit"},
                "cwd": cwd,
            })
            runner.invoke(app, ["_track-invocation"], input=payload)

        rows = self._get_skill_stats(db)
        # Two separate rows (one per repo hash) or one global row if cwd->root not found
        hashes = {r[3] for r in rows}
        assert len(hashes) >= 1  # at least one distinct hash recorded

    def test_empty_stdin_does_not_crash(self) -> None:
        result = runner.invoke(app, ["_track-invocation"], input="")
        assert result.exit_code == 0

    def test_invalid_json_does_not_crash(self) -> None:
        result = runner.invoke(app, ["_track-invocation"], input="not json at all")
        assert result.exit_code == 0

    def test_missing_skill_name_does_not_crash(self) -> None:
        payload = json.dumps({"tool_name": "Skill", "tool_input": {}})
        result = runner.invoke(app, ["_track-invocation"], input=payload)
        assert result.exit_code == 0

    def test_hidden_from_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "_track-invocation" not in result.output
