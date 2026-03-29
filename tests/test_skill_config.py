"""Tests for per-skill config (.sklab/config.yaml)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skill_lab.core.skill_config import (
    LastEvaluate,
    SkillConfig,
    load_config,
    resolve_model,
    save_config,
    update_evaluate,
    update_model,
)


@pytest.fixture()
def skill_dir(tmp_path: Path) -> Path:
    """Create a minimal skill directory with SKILL.md."""
    skill = tmp_path / "test-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: test-skill\n---\nBody text.")
    return skill


class TestLoadConfig:
    def test_missing_file_returns_defaults(self, skill_dir: Path) -> None:
        config = load_config(skill_dir)
        assert config == SkillConfig()
        assert config.version is None
        assert config.model is None
        assert config.last_evaluate is None

    def test_valid_config(self, skill_dir: Path) -> None:
        sklab = skill_dir / ".sklab"
        sklab.mkdir()
        (sklab / "config.yaml").write_text(
            yaml.dump({
                "version": "0.2.0",
                "llm": {"model": "gpt-4o"},
                "last-evaluate": {
                    "score": 85.5,
                    "checks-passed": 30,
                    "checks-total": 33,
                    "date": "2026-03-26T00:00:00Z",
                },
            })
        )
        config = load_config(skill_dir)
        assert config.version == "0.2.0"
        assert config.model == "gpt-4o"
        assert config.last_evaluate is not None
        assert config.last_evaluate.score == 85.5
        assert config.last_evaluate.checks_passed == 30
        assert config.last_evaluate.checks_total == 33
        assert config.last_evaluate.date == "2026-03-26T00:00:00Z"

    def test_corrupt_yaml_returns_defaults(self, skill_dir: Path) -> None:
        sklab = skill_dir / ".sklab"
        sklab.mkdir()
        (sklab / "config.yaml").write_text("{{invalid yaml: [")
        config = load_config(skill_dir)
        assert config == SkillConfig()

    def test_empty_file_returns_defaults(self, skill_dir: Path) -> None:
        sklab = skill_dir / ".sklab"
        sklab.mkdir()
        (sklab / "config.yaml").write_text("")
        config = load_config(skill_dir)
        assert config == SkillConfig()

    def test_non_dict_yaml_returns_defaults(self, skill_dir: Path) -> None:
        sklab = skill_dir / ".sklab"
        sklab.mkdir()
        (sklab / "config.yaml").write_text("just a string")
        config = load_config(skill_dir)
        assert config == SkillConfig()

    def test_partial_config_missing_llm(self, skill_dir: Path) -> None:
        sklab = skill_dir / ".sklab"
        sklab.mkdir()
        (sklab / "config.yaml").write_text(yaml.dump({"version": "1.0.0"}))
        config = load_config(skill_dir)
        assert config.version == "1.0.0"
        assert config.model is None
        assert config.last_evaluate is None

    def test_invalid_last_evaluate_returns_none(self, skill_dir: Path) -> None:
        sklab = skill_dir / ".sklab"
        sklab.mkdir()
        (sklab / "config.yaml").write_text(
            yaml.dump({"last-evaluate": {"score": "not-a-number"}})
        )
        config = load_config(skill_dir)
        assert config.last_evaluate is None

    def test_numeric_version_coerced_to_string(self, skill_dir: Path) -> None:
        sklab = skill_dir / ".sklab"
        sklab.mkdir()
        (sklab / "config.yaml").write_text(yaml.dump({"version": 0.1}))
        config = load_config(skill_dir)
        assert config.version == "0.1"


class TestSaveConfig:
    def test_creates_sklab_directory(self, skill_dir: Path) -> None:
        config = SkillConfig(version="0.1.0")
        save_config(skill_dir, config)
        assert (skill_dir / ".sklab" / "config.yaml").exists()

    def test_roundtrip(self, skill_dir: Path) -> None:
        original = SkillConfig(
            version="0.1.0",
            model="claude-haiku-4-5-20251001",
            last_evaluate=LastEvaluate(
                score=92.3,
                checks_passed=31,
                checks_total=33,
                date="2026-03-26T12:00:00Z",
            ),
        )
        save_config(skill_dir, original)
        loaded = load_config(skill_dir)
        assert loaded.version == original.version
        assert loaded.model == original.model
        assert loaded.last_evaluate is not None
        assert loaded.last_evaluate.score == 92.3
        assert loaded.last_evaluate.checks_passed == 31
        assert loaded.last_evaluate.checks_total == 33

    def test_empty_config_writes_empty_dict(self, skill_dir: Path) -> None:
        save_config(skill_dir, SkillConfig())
        text = (skill_dir / ".sklab" / "config.yaml").read_text()
        assert yaml.safe_load(text) == {}

    def test_score_rounded_to_one_decimal(self, skill_dir: Path) -> None:
        config = SkillConfig(
            last_evaluate=LastEvaluate(
                score=82.456789,
                checks_passed=30,
                checks_total=33,
                date="2026-03-26T00:00:00Z",
            ),
        )
        save_config(skill_dir, config)
        raw = yaml.safe_load((skill_dir / ".sklab" / "config.yaml").read_text())
        assert raw["last-evaluate"]["score"] == 82.5


class TestUpdateEvaluate:
    def test_creates_config_if_missing(self, skill_dir: Path) -> None:
        result = update_evaluate(
            skill_dir,
            score=75.0,
            checks_passed=28,
            checks_total=33,
            date="2026-03-26T00:00:00Z",
        )
        assert result.last_evaluate is not None
        assert result.last_evaluate.score == 75.0
        assert (skill_dir / ".sklab" / "config.yaml").exists()

    def test_preserves_existing_fields(self, skill_dir: Path) -> None:
        save_config(skill_dir, SkillConfig(version="0.1.0", model="gpt-4o"))
        update_evaluate(
            skill_dir,
            score=90.0,
            checks_passed=31,
            checks_total=33,
            date="2026-03-26T00:00:00Z",
        )
        config = load_config(skill_dir)
        assert config.version == "0.1.0"
        assert config.model == "gpt-4o"
        assert config.last_evaluate is not None
        assert config.last_evaluate.score == 90.0


class TestUpdateModel:
    def test_sets_model(self, skill_dir: Path) -> None:
        result = update_model(skill_dir, "gpt-4o")
        assert result.model == "gpt-4o"

    def test_preserves_existing_fields(self, skill_dir: Path) -> None:
        update_evaluate(
            skill_dir,
            score=80.0,
            checks_passed=29,
            checks_total=33,
            date="2026-03-26T00:00:00Z",
        )
        update_model(skill_dir, "gemini-2.0-flash")
        config = load_config(skill_dir)
        assert config.model == "gemini-2.0-flash"
        assert config.last_evaluate is not None
        assert config.last_evaluate.score == 80.0


class TestResolveModel:
    def test_flag_takes_priority(self, skill_dir: Path) -> None:
        save_config(skill_dir, SkillConfig(model="config-model"))
        result = resolve_model("flag-model", skill_dir)
        assert result == "flag-model"

    def test_config_model_used_when_no_flag(self, skill_dir: Path) -> None:
        save_config(skill_dir, SkillConfig(model="config-model"))
        result = resolve_model(None, skill_dir)
        assert result == "config-model"

    def test_env_var_used_when_no_flag_or_config(
        self, skill_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SKLAB_MODEL", "env-model")
        result = resolve_model(None, skill_dir)
        assert result == "env-model"

    def test_default_when_nothing_set(
        self, skill_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SKLAB_MODEL", raising=False)
        result = resolve_model(None, skill_dir)
        assert result == "claude-haiku-4-5-20251001"

    def test_flag_overrides_config_and_env(
        self, skill_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        save_config(skill_dir, SkillConfig(model="config-model"))
        monkeypatch.setenv("SKLAB_MODEL", "env-model")
        result = resolve_model("flag-model", skill_dir)
        assert result == "flag-model"

    def test_config_overrides_env(
        self, skill_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        save_config(skill_dir, SkillConfig(model="config-model"))
        monkeypatch.setenv("SKLAB_MODEL", "env-model")
        result = resolve_model(None, skill_dir)
        assert result == "config-model"
