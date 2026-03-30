"""Per-skill config file management (.sklab/config.yaml).

The config file is auto-created when commands persist data (evaluate, generate,
optimize) and is never required — all commands work identically without it.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from skill_lab.core.constants import CONFIG_FILE, SKILLLAB_DIR
from skill_lab.core.llm import DEFAULT_MODEL

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LastEvaluate:
    """Snapshot of the most recent evaluation run."""

    score: float
    checks_passed: int
    checks_total: int
    date: str


@dataclass(frozen=True)
class LastReview:
    """Snapshot of the most recent LLM judge review."""

    judge_score: float
    activation_score: float
    instruction_score: float
    date: str


@dataclass(frozen=True)
class SkillConfig:
    """Per-skill configuration stored in .sklab/config.yaml."""

    version: str | None = None
    model: str | None = None
    last_evaluate: LastEvaluate | None = None
    last_review: LastReview | None = None


def _config_path(skill_path: Path) -> Path:
    return skill_path / CONFIG_FILE


def _parse_last_evaluate(raw: dict[str, Any]) -> LastEvaluate | None:
    """Parse the last-evaluate section, returning None if invalid."""
    le = raw.get("last-evaluate")
    if not isinstance(le, dict):
        return None
    try:
        return LastEvaluate(
            score=float(le["score"]),
            checks_passed=int(le["checks-passed"]),
            checks_total=int(le["checks-total"]),
            date=str(le["date"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _parse_last_review(raw: dict[str, Any]) -> LastReview | None:
    """Parse the last-review section, returning None if invalid."""
    lr = raw.get("last-review")
    if not isinstance(lr, dict):
        return None
    try:
        return LastReview(
            judge_score=float(lr["judge-score"]),
            activation_score=float(lr["activation-score"]),
            instruction_score=float(lr["instruction-score"]),
            date=str(lr["date"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _parse_model(raw: dict[str, Any]) -> str | None:
    """Extract the LLM model from the llm section."""
    llm = raw.get("llm")
    if isinstance(llm, dict):
        model = llm.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
    return None


def load_config(skill_path: Path) -> SkillConfig:
    """Load .sklab/config.yaml, returning defaults if missing or corrupt."""
    path = _config_path(skill_path)
    if not path.exists():
        return SkillConfig()

    try:
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
    except Exception:
        logger.warning("Corrupt config at %s, using defaults", path)
        return SkillConfig()

    if not isinstance(raw, dict):
        return SkillConfig()

    version = raw.get("version")
    if version is not None:
        version = str(version)

    return SkillConfig(
        version=version,
        model=_parse_model(raw),
        last_evaluate=_parse_last_evaluate(raw),
        last_review=_parse_last_review(raw),
    )


def save_config(skill_path: Path, config: SkillConfig) -> None:
    """Write config to .sklab/config.yaml, creating the directory if needed."""
    sklab_dir = skill_path / SKILLLAB_DIR
    sklab_dir.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {}

    if config.version is not None:
        data["version"] = config.version

    if config.model is not None:
        data["llm"] = {"model": config.model}

    if config.last_evaluate is not None:
        le = config.last_evaluate
        data["last-evaluate"] = {
            "score": round(le.score, 1),
            "checks-passed": le.checks_passed,
            "checks-total": le.checks_total,
            "date": le.date,
        }

    if config.last_review is not None:
        lr = config.last_review
        data["last-review"] = {
            "judge-score": round(lr.judge_score, 1),
            "activation-score": round(lr.activation_score, 1),
            "instruction-score": round(lr.instruction_score, 1),
            "date": lr.date,
        }

    path = _config_path(skill_path)
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def update_evaluate(
    skill_path: Path,
    *,
    score: float,
    checks_passed: int,
    checks_total: int,
    date: str,
) -> SkillConfig:
    """Update the last-evaluate snapshot, preserving other fields."""
    config = load_config(skill_path)
    updated = SkillConfig(
        version=config.version,
        model=config.model,
        last_evaluate=LastEvaluate(
            score=score,
            checks_passed=checks_passed,
            checks_total=checks_total,
            date=date,
        ),
        last_review=config.last_review,
    )
    save_config(skill_path, updated)
    return updated


def update_model(skill_path: Path, model: str) -> SkillConfig:
    """Set the preferred LLM model, preserving other fields."""
    config = load_config(skill_path)
    updated = SkillConfig(
        version=config.version,
        model=model,
        last_evaluate=config.last_evaluate,
        last_review=config.last_review,
    )
    save_config(skill_path, updated)
    return updated


def update_review(
    skill_path: Path,
    *,
    judge_score: float,
    activation_score: float,
    instruction_score: float,
    date: str,
) -> SkillConfig:
    """Update the last-review snapshot, preserving other fields."""
    config = load_config(skill_path)
    updated = SkillConfig(
        version=config.version,
        model=config.model,
        last_evaluate=config.last_evaluate,
        last_review=LastReview(
            judge_score=judge_score,
            activation_score=activation_score,
            instruction_score=instruction_score,
            date=date,
        ),
    )
    save_config(skill_path, updated)
    return updated


def resolve_model(flag_model: str | None, skill_path: Path) -> str:
    """Resolve the LLM model using the priority chain.

    Resolution order:
        1. --model CLI flag (highest)
        2. .sklab/config.yaml llm.model
        3. SKLAB_MODEL environment variable
        4. DEFAULT_MODEL constant
    """
    if flag_model:
        return flag_model
    config = load_config(skill_path)
    if config.model:
        return config.model
    return os.environ.get("SKLAB_MODEL") or DEFAULT_MODEL
