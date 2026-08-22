from __future__ import annotations

import json
from pathlib import Path

import pytest
from congreso_debates.config import Config


def test_default_config() -> None:
    cfg = Config()
    assert len(cfg.legislatures) == 15
    assert cfg.max_sessions_per_leg is None
    assert cfg.raw_dir == Path("data/raw")
    assert cfg.download_speech_pdfs is True


def test_config_load_and_validate(tmp_path: Path) -> None:
    data = {
        "legislatures": [14, 15],
        "max_sessions_per_leg": 10,
        "download_speech_pdfs": True,
        "max_speech_pdfs": 50,
    }
    cfg_file = tmp_path / "test_cfg.json"
    cfg_file.write_text(json.dumps(data), encoding="utf-8")

    cfg = Config.load(cfg_file)
    assert cfg.legislatures == [14, 15]
    assert cfg.max_sessions_per_leg == 10
    assert cfg.max_speech_pdfs == 50


def test_config_invalid() -> None:
    cfg = Config(max_sessions_per_leg=0)
    with pytest.raises(ValueError, match="max_sessions_per_leg"):
        cfg.validate()
