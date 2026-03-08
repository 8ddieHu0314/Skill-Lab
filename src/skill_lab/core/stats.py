"""Stats query functions for sklab stats commands.

Reads from ~/.sklab/usage.db to produce per-user usage statistics.
All query functions return empty/None when the DB does not exist yet.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from skill_lab.core.constants import SKLAB_DB


@dataclass
class OverviewStats:
    skills_fired_this_month: int
    month_label: str
    avg_baseline_score: float | None
    avg_current_score: float | None
    tokens_this_month: int
    version_history: list[tuple[str, str]]  # (version, first_seen_date)
    has_old_data: bool  # rows recorded before stats columns were added


@dataclass
class SkillCount:
    skill_name: str
    use_count: int
    tokens_used: int


@dataclass
class SkillScore:
    skill_name: str
    current_score: float
    baseline_score: float
    is_new: bool  # only one evaluate run exists (baseline == current)


@dataclass
class SkillTokens:
    skill_name: str
    tokens_per_invocation: int
    total_tokens: int


def _month_label() -> str:
    """Return e.g. 'Mar 2026  (Mar 1 – Mar 7, 2026)' for the current month."""
    now = datetime.now()
    start = now.strftime(f"%b 1, %Y")
    today = now.strftime("%b %-d, %Y")
    return f"{now.strftime('%b %Y')}  ({start} \u2013 {today})"


def _current_ym() -> str:
    return datetime.now().strftime("%Y-%m")


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(SKLAB_DB)


def get_overview_stats() -> OverviewStats | None:
    """Return overview stats, or None if the DB doesn't exist yet."""
    if not Path(SKLAB_DB).exists():
        return None

    with _conn() as conn:
        fired: int = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE command = 'skill-invoke'
              AND strftime('%Y-%m', timestamp) = ?
            """,
            (_current_ym(),),
        ).fetchone()[0]

        # Baseline: first evaluate score per skill, then average across skills
        avg_baseline: float | None = conn.execute(
            """
            SELECT AVG(score) FROM (
                SELECT e.score FROM events e
                WHERE e.command = 'evaluate'
                  AND e.skill_name IS NOT NULL
                  AND e.score IS NOT NULL
                  AND e.id = (
                      SELECT MIN(id) FROM events
                      WHERE command = 'evaluate'
                        AND skill_name = e.skill_name
                        AND skill_name IS NOT NULL
                        AND score IS NOT NULL
                  )
            )
            """
        ).fetchone()[0]

        # Current: latest evaluate score per skill, then average
        avg_current: float | None = conn.execute(
            """
            SELECT AVG(score) FROM (
                SELECT e.score FROM events e
                WHERE e.command = 'evaluate'
                  AND e.skill_name IS NOT NULL
                  AND e.score IS NOT NULL
                  AND e.id = (
                      SELECT MAX(id) FROM events
                      WHERE command = 'evaluate'
                        AND skill_name = e.skill_name
                        AND skill_name IS NOT NULL
                        AND score IS NOT NULL
                  )
            )
            """
        ).fetchone()[0]

        tokens: int = conn.execute(
            """
            SELECT COALESCE(SUM(input_tokens), 0) FROM events
            WHERE command = 'skill-invoke'
              AND strftime('%Y-%m', timestamp) = ?
            """,
            (_current_ym(),),
        ).fetchone()[0]

        version_rows = conn.execute(
            """
            SELECT sklab_version, MIN(timestamp) as first_seen
            FROM events
            WHERE sklab_version IS NOT NULL
            GROUP BY sklab_version
            ORDER BY first_seen ASC
            """
        ).fetchall()

        # Old data: evaluate rows written before stats columns existed (skill_name is NULL)
        has_old: bool = (
            conn.execute(
                """
                SELECT COUNT(*) FROM events
                WHERE command = 'evaluate' AND skill_name IS NULL
                """
            ).fetchone()[0]
            > 0
        )

    version_history = [
        (v, datetime.fromisoformat(ts).strftime("%b %d, %Y"))
        for v, ts in version_rows
        if v
    ]

    return OverviewStats(
        skills_fired_this_month=fired,
        month_label=_month_label(),
        avg_baseline_score=avg_baseline,
        avg_current_score=avg_current,
        tokens_this_month=tokens or 0,
        version_history=version_history,
        has_old_data=has_old,
    )


def get_stats_count(
    repo_root: Path | None = None,
) -> tuple[str, list[SkillCount]]:
    """Return (month_label, rows) for sklab stats count.

    If repo_root is given, only skills whose skill_path starts with that
    directory are included (for --here filtering).
    """
    label = _month_label()
    if not Path(SKLAB_DB).exists():
        return label, []

    path_clause = "AND skill_path LIKE ?" if repo_root else ""
    params: list[object] = [_current_ym()]
    if repo_root:
        params.append(str(repo_root).rstrip("/") + "/%")

    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT skill_name,
                   COUNT(*) as use_count,
                   COALESCE(SUM(input_tokens), 0) as tokens
            FROM events
            WHERE command = 'skill-invoke'
              AND skill_name IS NOT NULL
              AND strftime('%Y-%m', timestamp) = ?
              {path_clause}
            GROUP BY skill_name
            ORDER BY use_count DESC
            """,
            params,
        ).fetchall()

    return label, [SkillCount(r[0], r[1], r[2]) for r in rows]


def get_stats_score(
    repo_root: Path | None = None,
) -> list[SkillScore]:
    """Return per-skill score data for sklab stats score.

    If repo_root is given, only skills whose skill_path starts with that
    directory are included (for --here filtering).
    """
    if not Path(SKLAB_DB).exists():
        return []

    path_clause = "AND skill_path LIKE ?" if repo_root else ""
    path_param = [str(repo_root).rstrip("/") + "/%"] if repo_root else []

    with _conn() as conn:
        # For each skill: min_id, max_id, and their scores
        # A skill is "new" when min_id == max_id (only one evaluate run)
        skill_ids = conn.execute(
            f"""
            SELECT skill_name, MIN(id) as min_id, MAX(id) as max_id
            FROM events
            WHERE command = 'evaluate'
              AND skill_name IS NOT NULL
              AND score IS NOT NULL
              {path_clause}
            GROUP BY skill_name
            ORDER BY skill_name
            """,
            path_param,
        ).fetchall()

        if not skill_ids:
            return []

        id_to_score: dict[int, float] = {
            row[0]: row[1]
            for row in conn.execute(
                f"""
                SELECT id, score FROM events
                WHERE id IN ({','.join('?' * len(skill_ids) * 2)})
                  AND score IS NOT NULL
                """,
                [sid for _, mn, mx in skill_ids for sid in (mn, mx)],
            ).fetchall()
        }

    result = []
    for skill_name, min_id, max_id in skill_ids:
        baseline = id_to_score.get(min_id, 0.0)
        current = id_to_score.get(max_id, baseline)
        result.append(
            SkillScore(
                skill_name=skill_name,
                current_score=current,
                baseline_score=baseline,
                is_new=(min_id == max_id),
            )
        )
    return result


def get_stats_tokens(
    repo_root: Path | None = None,
) -> tuple[str, list[SkillTokens]]:
    """Return (month_label, rows) for sklab stats tokens.

    If repo_root is given, only skills whose skill_path starts with that
    directory are included (for --here filtering).
    """
    label = _month_label()
    if not Path(SKLAB_DB).exists():
        return label, []

    path_clause = "AND skill_path LIKE ?" if repo_root else ""
    params: list[object] = [_current_ym()]
    if repo_root:
        params.append(str(repo_root).rstrip("/") + "/%")

    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT skill_name,
                   CAST(AVG(input_tokens) AS INTEGER) as avg_tokens,
                   COALESCE(SUM(input_tokens), 0) as total_tokens
            FROM events
            WHERE command = 'skill-invoke'
              AND skill_name IS NOT NULL
              AND input_tokens IS NOT NULL
              AND strftime('%Y-%m', timestamp) = ?
              {path_clause}
            GROUP BY skill_name
            ORDER BY total_tokens DESC
            """,
            params,
        ).fetchall()

    return label, [SkillTokens(r[0], r[1] or 0, r[2]) for r in rows]
