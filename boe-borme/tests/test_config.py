from __future__ import annotations

import json

import pytest

from boe_borme.config import Config


def test_load_resolves_relative_paths(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    path = config_dir / "default.json"
    path.write_text(
        json.dumps(
            {
                "raw_dir": "data/raw",
                "processed_dir": "data/processed",
                "artifacts_dir": "artifacts",
                "state_dir": "state",
                "staging_dir": "hf_staging",
            }
        ),
        encoding="utf-8",
    )
    config = Config.load(path)
    assert config.raw_dir == tmp_path / "data" / "raw"
    assert config.processed_dir == tmp_path / "data" / "processed"


def test_unknown_key_is_rejected(tmp_path):
    path = tmp_path / "nope.json"
    path.write_text(json.dumps({"raw_dir": "a", "mystery": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown configuration keys"):
        Config.load(path)


def test_invalid_date_rejected(make_config):
    with pytest.raises(ValueError):
        make_config(boe_start_date="1960/09/01")


def test_end_before_start_rejected(make_config):
    with pytest.raises(ValueError):
        make_config(boe_start_date="2024-01-10", end_date="2024-01-01")


def test_default_dates(make_config):
    config = make_config()
    assert config.resolved_end_date
    assert config.start_for("boe_sumario").isoformat() == "1960-09-01"
    assert config.start_for("borme_sumario").isoformat() == "2009-01-01"
