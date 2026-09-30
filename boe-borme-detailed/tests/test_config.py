from __future__ import annotations

import json

import pytest

from boe_borme_detailed.config import Config


def test_unknown_key_rejected(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"base_processed_dir": "b", "nope": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown configuration keys"):
        Config.load(path)


def test_processed_equal_base_rejected(make_config):
    config = make_config()
    with pytest.raises(ValueError, match="must differ"):
        make_config(processed_dir=config.base_processed_dir)


def test_load_resolves_relative_paths(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    path = config_dir / "default.json"
    path.write_text(
        json.dumps(
            {
                "base_processed_dir": "base/data/processed",
                "processed_dir": "data/processed",
                "artifacts_dir": "artifacts",
                "state_dir": "state",
                "staging_dir": "hf_staging",
            }
        ),
        encoding="utf-8",
    )
    config = Config.load(path)
    assert config.base_processed_dir == (tmp_path / "base" / "data" / "processed").resolve()
    assert config.processed_dir == (tmp_path / "data" / "processed").resolve()
