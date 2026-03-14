"""Tests for sklab stats DB query functions and CLI commands."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from skill_lab.cli import app
from skill_lab.core import stats as stats_module
from skill_lab.core.stats import (
    SkillCount,
    SkillScore,
    SkillTokens,
    get_overview_stats,
    get_stats_count,
    get_stats_score,
    get_stats_tokens,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect SKLAB_DB to a temporary path and return it."""
    db_path = tmp_path / "usage.db"
    monkeypatch.setattr(stats_module, "SKLAB_DB", db_path)
    # Also patch the constant imported directly in stats.py Path checks
    monkeypatch.setattr("skill_lab.core.stats.SKLAB_DB", db_path)
    return db_path


def _create_db(db_path: Path) -> sqlite3.Connection:
    """Create all telemetry tables."""
    conn = sqlite3.connect(db_path)
    # Legacy events table — kept for has_old_data check
    conn.execute("""
        CREATE TABLE events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_uuid     TEXT    NOT NULL,
            command       TEXT    NOT NULL,
            duration_ms   REAL,
            exit_code     INTEGER,
            sklab_version TEXT,
            platform      TEXT,
            python_version TEXT,
            timestamp     TEXT    NOT NULL,
            synced        INTEGER DEFAULT 0,
            skill_name    TEXT,
            score         REAL,
            input_tokens  INTEGER,
            skill_path    TEXT
        )
    """)
    # New normalized tables
    conn.execute("""
        CREATE TABLE command_events (
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
        CREATE TABLE skill_events (
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
        CREATE TABLE skill_stats (
            skill_name       TEXT NOT NULL,
            month            TEXT NOT NULL,
            repo_root_hash   TEXT NOT NULL DEFAULT '',
            use_count        INTEGER NOT NULL DEFAULT 0,
            total_tokens     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (skill_name, month, repo_root_hash)
        )
    """)
    conn.commit()
    return conn


def _insert_skill_stats(
    conn: sqlite3.Connection,
    skill_name: str,
    use_count: int = 1,
    total_tokens: int = 0,
    month: str | None = None,
    repo_root_hash: str = "",
) -> None:
    m = month or _ts()[:7]
    conn.execute(
        """
        INSERT INTO skill_stats (skill_name, month, repo_root_hash, use_count, total_tokens)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(skill_name, month, repo_root_hash) DO UPDATE SET
            use_count    = use_count + excluded.use_count,
            total_tokens = total_tokens + excluded.total_tokens
        """,
        (skill_name, m, repo_root_hash, use_count, total_tokens),
    )
    conn.commit()


def _ts(year: int = 2026, month: int = 3, day: int = 5) -> str:
    return datetime(year, month, day, tzinfo=timezone.utc).isoformat()


def _insert(
    conn: sqlite3.Connection,
    command: str,
    skill_name: str | None = None,
    score: float | None = None,
    input_tokens: int | None = None,
    sklab_version: str = "0.4.0",
    timestamp: str | None = None,
    skill_path: str | None = None,
) -> None:
    ts = timestamp or _ts()
    conn.execute(
        """
        INSERT INTO command_events
            (install_uuid, session_uuid, sklab_version, command,
             duration_ms, exit_code, success, timestamp, synced)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        ("test-uuid", "test-session", sklab_version, command, 100.0, 0, 1, ts),
    )
    cmd_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    has_skill_data = any(v is not None for v in (skill_name, score, input_tokens, skill_path))
    if has_skill_data:
        conn.execute(
            """
            INSERT INTO skill_events
                (command_event_id, install_uuid, skill_name, score, input_tokens,
                 skill_path, timestamp, synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (cmd_id, "test-uuid", skill_name, score, input_tokens, skill_path, ts),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# get_overview_stats
# ---------------------------------------------------------------------------


class TestGetOverviewStats:
    def test_returns_none_when_db_missing(self, tmp_db: Path) -> None:
        assert get_overview_stats() is None

    def test_empty_db_returns_zeros(self, tmp_db: Path) -> None:
        _create_db(tmp_db)
        result = get_overview_stats()
        assert result is not None
        assert result.skills_fired_this_month == 0
        assert result.avg_baseline_score is None
        assert result.avg_current_score is None
        assert result.tokens_this_month == 0
        assert result.version_history == []
        assert result.has_old_data is False

    def test_counts_skill_invokes_this_month(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=2, total_tokens=400)
        _insert_skill_stats(conn, "review-pr", use_count=1, total_tokens=150)
        result = get_overview_stats()
        assert result is not None
        assert result.skills_fired_this_month == 3

    def test_ignores_invokes_from_other_months(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=200, month="2026-02")
        result = get_overview_stats()
        assert result is not None
        assert result.skills_fired_this_month == 0

    def test_avg_scores_baseline_and_current(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        # commit: first=60, latest=80
        _insert(conn, "evaluate", skill_name="commit", score=60.0, timestamp=_ts(day=1))
        _insert(conn, "evaluate", skill_name="commit", score=80.0, timestamp=_ts(day=5))
        # review-pr: first=70, latest=90
        _insert(conn, "evaluate", skill_name="review-pr", score=70.0, timestamp=_ts(day=1))
        _insert(conn, "evaluate", skill_name="review-pr", score=90.0, timestamp=_ts(day=5))
        result = get_overview_stats()
        assert result is not None
        assert result.avg_baseline_score == pytest.approx(65.0)  # (60+70)/2
        assert result.avg_current_score == pytest.approx(85.0)   # (80+90)/2

    def test_sums_tokens_this_month(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=300)
        _insert_skill_stats(conn, "review-pr", use_count=1, total_tokens=200)
        result = get_overview_stats()
        assert result is not None
        assert result.tokens_this_month == 500

    def test_version_history(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert(conn, "evaluate", sklab_version="0.3.0", timestamp=_ts(2026, 1, 1))
        _insert(conn, "evaluate", sklab_version="0.4.0", timestamp=_ts(2026, 2, 1))
        result = get_overview_stats()
        assert result is not None
        versions = [v for v, _ in result.version_history]
        assert versions == ["0.3.0", "0.4.0"]

    def test_detects_old_data(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        # Simulate old-style row in the legacy events table (skill_name IS NULL)
        conn.execute(
            "INSERT INTO events (user_uuid, command, timestamp) VALUES (?, ?, ?)",
            ("test-uuid", "evaluate", _ts()),
        )
        conn.commit()
        result = get_overview_stats()
        assert result is not None
        assert result.has_old_data is True

    def test_no_old_data_when_all_rows_have_skill_name(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert(conn, "evaluate", skill_name="commit", score=80.0)
        result = get_overview_stats()
        assert result is not None
        assert result.has_old_data is False

    def test_month_label_contains_current_month(self, tmp_db: Path) -> None:
        _create_db(tmp_db)
        result = get_overview_stats()
        assert result is not None
        now = datetime.now()
        assert now.strftime("%b %Y") in result.month_label

    def test_month_label_no_platform_specific_format(self, tmp_db: Path) -> None:
        """Month label must not use %-d (Linux-only) — uses str(day) instead."""
        from skill_lab.core.stats import _month_label
        label = _month_label()
        # Should not raise and should contain the numeric day without zero-padding
        now = datetime.now()
        assert str(now.day) in label


# ---------------------------------------------------------------------------
# get_stats_count
# ---------------------------------------------------------------------------


class TestGetStatsCount:
    def test_empty_when_db_missing(self, tmp_db: Path) -> None:
        label, rows = get_stats_count()
        assert rows == []

    def test_empty_when_no_invocations(self, tmp_db: Path) -> None:
        _create_db(tmp_db)
        label, rows = get_stats_count()
        assert rows == []

    def test_counts_per_skill(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=2, total_tokens=400)
        _insert_skill_stats(conn, "review-pr", use_count=1, total_tokens=150)
        _, rows = get_stats_count()
        assert len(rows) == 2
        commit_row = next(r for r in rows if r.skill_name == "commit")
        assert commit_row.use_count == 2
        assert commit_row.tokens_used == 400
        review_row = next(r for r in rows if r.skill_name == "review-pr")
        assert review_row.use_count == 1
        assert review_row.tokens_used == 150

    def test_ordered_by_use_count_desc(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "rare", use_count=1)
        _insert_skill_stats(conn, "popular", use_count=2)
        _, rows = get_stats_count()
        assert rows[0].skill_name == "popular"

    def test_excludes_other_months(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, month="2026-01")
        _, rows = get_stats_count()
        assert rows == []

    def test_returns_skill_count_dataclass(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=100)
        _, rows = get_stats_count()
        assert isinstance(rows[0], SkillCount)


# ---------------------------------------------------------------------------
# get_stats_score
# ---------------------------------------------------------------------------


class TestGetStatsScore:
    def test_empty_when_db_missing(self, tmp_db: Path) -> None:
        assert get_stats_score() == []

    def test_empty_when_no_evaluates(self, tmp_db: Path) -> None:
        _create_db(tmp_db)
        assert get_stats_score() == []

    def test_single_run_is_new(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert(conn, "evaluate", skill_name="commit", score=80.0)
        rows = get_stats_score()
        assert len(rows) == 1
        assert rows[0].is_new is True
        assert rows[0].current_score == 80.0
        assert rows[0].baseline_score == 80.0

    def test_multiple_runs_tracks_baseline_and_current(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert(conn, "evaluate", skill_name="commit", score=60.0, timestamp=_ts(day=1))
        _insert(conn, "evaluate", skill_name="commit", score=75.0, timestamp=_ts(day=3))
        _insert(conn, "evaluate", skill_name="commit", score=88.0, timestamp=_ts(day=5))
        rows = get_stats_score()
        assert len(rows) == 1
        assert rows[0].baseline_score == 60.0
        assert rows[0].current_score == 88.0
        assert rows[0].is_new is False

    def test_multiple_skills(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert(conn, "evaluate", skill_name="commit", score=70.0)
        _insert(conn, "evaluate", skill_name="review-pr", score=85.0)
        rows = get_stats_score()
        assert len(rows) == 2
        names = {r.skill_name for r in rows}
        assert names == {"commit", "review-pr"}

    def test_rows_sorted_by_skill_name(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert(conn, "evaluate", skill_name="zebra", score=70.0)
        _insert(conn, "evaluate", skill_name="apple", score=80.0)
        rows = get_stats_score()
        assert rows[0].skill_name == "apple"
        assert rows[1].skill_name == "zebra"

    def test_returns_skill_score_dataclass(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert(conn, "evaluate", skill_name="commit", score=80.0)
        rows = get_stats_score()
        assert isinstance(rows[0], SkillScore)

    def test_skips_rows_without_score(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert(conn, "evaluate", skill_name="commit", score=None)
        rows = get_stats_score()
        assert rows == []


# ---------------------------------------------------------------------------
# get_stats_tokens
# ---------------------------------------------------------------------------


class TestGetStatsTokens:
    def test_empty_when_db_missing(self, tmp_db: Path) -> None:
        _, rows = get_stats_tokens()
        assert rows == []

    def test_empty_when_no_data(self, tmp_db: Path) -> None:
        _create_db(tmp_db)
        _, rows = get_stats_tokens()
        assert rows == []

    def test_aggregates_per_skill(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=2, total_tokens=400)
        _insert_skill_stats(conn, "review-pr", use_count=1, total_tokens=400)
        _, rows = get_stats_tokens()
        commit_row = next(r for r in rows if r.skill_name == "commit")
        assert commit_row.total_tokens == 400
        assert commit_row.tokens_per_invocation == 200

    def test_ordered_by_total_desc(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "cheap", use_count=1, total_tokens=10)
        _insert_skill_stats(conn, "expensive", use_count=1, total_tokens=1000)
        _, rows = get_stats_tokens()
        assert rows[0].skill_name == "expensive"

    def test_excludes_other_months(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=200, month="2025-01")
        _, rows = get_stats_tokens()
        assert rows == []

    def test_returns_skill_tokens_dataclass(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=200)
        _, rows = get_stats_tokens()
        assert isinstance(rows[0], SkillTokens)

    def test_skips_rows_without_tokens(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=0)
        _, rows = get_stats_tokens()
        assert rows == []


# ---------------------------------------------------------------------------
# CLI: sklab stats (overview)
# ---------------------------------------------------------------------------


class TestStatsCLI:
    def test_stats_no_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("skill_lab.core.stats.SKLAB_DB", tmp_path / "usage.db")
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "No usage data" in result.output

    def test_stats_with_data(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db = tmp_path / "usage.db"
        monkeypatch.setattr("skill_lab.core.stats.SKLAB_DB", db)
        conn = _create_db(db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=200)
        _insert(conn, "evaluate", skill_name="commit", score=80.0)
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "sklab stats" in result.output

    def test_stats_count_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db = tmp_path / "usage.db"
        monkeypatch.setattr("skill_lab.core.stats.SKLAB_DB", db)
        _create_db(db)
        result = runner.invoke(app, ["stats", "count"])
        assert result.exit_code == 0
        assert "No skill invocations" in result.output

    def test_stats_count_with_data(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db = tmp_path / "usage.db"
        monkeypatch.setattr("skill_lab.core.stats.SKLAB_DB", db)
        conn = _create_db(db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=200)
        result = runner.invoke(app, ["stats", "count"])
        assert result.exit_code == 0
        assert "commit" in result.output

    def test_stats_score_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db = tmp_path / "usage.db"
        monkeypatch.setattr("skill_lab.core.stats.SKLAB_DB", db)
        _create_db(db)
        result = runner.invoke(app, ["stats", "score"])
        assert result.exit_code == 0
        assert "No evaluate runs" in result.output

    def test_stats_score_with_data(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db = tmp_path / "usage.db"
        monkeypatch.setattr("skill_lab.core.stats.SKLAB_DB", db)
        conn = _create_db(db)
        _insert(conn, "evaluate", skill_name="commit", score=80.0, timestamp=_ts(day=1))
        _insert(conn, "evaluate", skill_name="commit", score=90.0, timestamp=_ts(day=5))
        result = runner.invoke(app, ["stats", "score"])
        assert result.exit_code == 0
        assert "commit" in result.output
        assert "80.0" in result.output
        assert "90.0" in result.output

    def test_stats_tokens_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db = tmp_path / "usage.db"
        monkeypatch.setattr("skill_lab.core.stats.SKLAB_DB", db)
        _create_db(db)
        result = runner.invoke(app, ["stats", "tokens"])
        assert result.exit_code == 0
        assert "No token data" in result.output

    def test_stats_tokens_with_data(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db = tmp_path / "usage.db"
        monkeypatch.setattr("skill_lab.core.stats.SKLAB_DB", db)
        conn = _create_db(db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=300)
        result = runner.invoke(app, ["stats", "tokens"])
        assert result.exit_code == 0
        assert "commit" in result.output
        assert "300" in result.output


# ---------------------------------------------------------------------------
# --here filtering (repo_root)
# ---------------------------------------------------------------------------


class TestRepoFilter:
    import hashlib as _hashlib

    REPO_A = "/projects/repo-a"
    REPO_B = "/projects/repo-b"
    HASH_A = _hashlib.sha256(REPO_A.encode()).hexdigest()
    HASH_B = _hashlib.sha256(REPO_B.encode()).hexdigest()

    def test_count_filters_by_repo(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=100, repo_root_hash=self.HASH_A)
        _insert_skill_stats(conn, "pdf", use_count=1, total_tokens=100, repo_root_hash=self.HASH_B)
        _, rows = get_stats_count(repo_root_hash=self.HASH_A)
        assert len(rows) == 1
        assert rows[0].skill_name == "commit"

    def test_count_global_returns_all(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=100, repo_root_hash=self.HASH_A)
        _insert_skill_stats(conn, "pdf", use_count=1, total_tokens=100, repo_root_hash=self.HASH_B)
        _, rows = get_stats_count()
        assert len(rows) == 2

    def test_score_not_filtered_by_repo(self, tmp_db: Path) -> None:
        """Score data in skill_events is always global — repo hash is ignored."""
        conn = _create_db(tmp_db)
        _insert(conn, "evaluate", skill_name="commit", score=80.0,
                skill_path=f"{self.REPO_A}/commit")
        _insert(conn, "evaluate", skill_name="pdf", score=70.0,
                skill_path=f"{self.REPO_B}/pdf")
        rows = get_stats_score(repo_root_hash=self.HASH_A)
        # Both skills returned — score view is global
        assert len(rows) == 2

    def test_score_global_returns_all(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert(conn, "evaluate", skill_name="commit", score=80.0,
                skill_path=f"{self.REPO_A}/commit")
        _insert(conn, "evaluate", skill_name="pdf", score=70.0,
                skill_path=f"{self.REPO_B}/pdf")
        rows = get_stats_score()
        assert len(rows) == 2

    def test_tokens_filters_by_repo(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=200, repo_root_hash=self.HASH_A)
        _insert_skill_stats(conn, "pdf", use_count=1, total_tokens=400, repo_root_hash=self.HASH_B)
        _, rows = get_stats_tokens(repo_root_hash=self.HASH_A)
        assert len(rows) == 1
        assert rows[0].skill_name == "commit"

    def test_tokens_global_returns_all(self, tmp_db: Path) -> None:
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=200, repo_root_hash=self.HASH_A)
        _insert_skill_stats(conn, "pdf", use_count=1, total_tokens=400, repo_root_hash=self.HASH_B)
        _, rows = get_stats_tokens()
        assert len(rows) == 2

    def test_filter_unknown_hash_returns_empty(self, tmp_db: Path) -> None:
        """--here with a hash that has no matching rows returns empty."""
        conn = _create_db(tmp_db)
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=100, repo_root_hash=self.HASH_B)
        _, rows = get_stats_count(repo_root_hash=self.HASH_A)
        assert rows == []

    def test_cli_stats_count_here_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import hashlib

        db = tmp_path / "usage.db"
        repo = tmp_path / "my-repo"
        repo.mkdir()
        monkeypatch.setattr("skill_lab.core.stats.SKLAB_DB", db)
        conn = _create_db(db)
        repo_hash = hashlib.sha256(str(repo).encode()).hexdigest()
        other_hash = hashlib.sha256(b"/other/repo").hexdigest()
        _insert_skill_stats(conn, "commit", use_count=1, total_tokens=100, repo_root_hash=repo_hash)
        _insert_skill_stats(conn, "pdf", use_count=1, total_tokens=100, repo_root_hash=other_hash)
        monkeypatch.chdir(repo)
        # Simulate being inside the repo (no .git, falls back to cwd)
        result = runner.invoke(app, ["stats", "count", "--here"])
        assert result.exit_code == 0
        assert "commit" in result.output
        assert "pdf" not in result.output
