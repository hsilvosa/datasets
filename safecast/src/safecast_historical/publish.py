from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Config

HEADER = """---
license: cc0-1.0
language:
- en
pretty_name: Safecast Historical Radiation Measurements
tags:
- geospatial
- radiation
- environment
- time-series
- citizen-science
configs:
- config_name: measurements
  data_files:
  - split: train
    path: data/measurements/*.parquet
---
"""


def stage(config: Config) -> Path:
    if config.staging_dir.exists():
        shutil.rmtree(config.staging_dir)
    data = config.staging_dir / "data" / "measurements"
    artifacts = config.staging_dir / "artifacts"
    data.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    for source in sorted((config.processed_dir / "measurements").glob("*.parquet")):
        shutil.copy2(source, data / source.name)
    for source in sorted(config.artifacts_dir.glob("*.json")):
        shutil.copy2(source, artifacts / source.name)
    card = Path(__file__).resolve().parents[2] / "DATASET_CARD.md"
    (config.staging_dir / "README.md").write_text(
        HEADER + "\n" + card.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return config.staging_dir


def upload(config: Config, repo_id: str) -> None:
    subprocess.run(
        ["hf", "upload", repo_id, str(stage(config)), ".", "--repo-type", "dataset"],
        check=True,
    )
