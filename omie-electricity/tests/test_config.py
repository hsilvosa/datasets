from pathlib import Path
import pytest
from omie_electricity.config import Config


def test_config_load(tmp_path: Path):
    cfg_file = tmp_path / "cfg.json"
    cfg_file.write_text("""{
        "start_date": "2024-01-01",
        "end_date": "2024-01-05",
        "raw_dir": "data/raw",
        "processed_dir": "data/processed",
        "artifacts_dir": "artifacts",
        "staging_dir": "hf_staging"
    }""")
    config = Config.load(cfg_file)
    assert config.start_date == "2024-01-01"
    assert config.end_date == "2024-01-05"


def test_config_invalid_date(tmp_path: Path):
    cfg_file = tmp_path / "cfg.json"
    cfg_file.write_text("""{
        "start_date": "2024-01-10",
        "end_date": "2024-01-05",
        "raw_dir": "data/raw",
        "processed_dir": "data/processed",
        "artifacts_dir": "artifacts",
        "staging_dir": "hf_staging"
    }""")
    with pytest.raises(ValueError, match="end_date must not be before start_date"):
        Config.load(cfg_file)
