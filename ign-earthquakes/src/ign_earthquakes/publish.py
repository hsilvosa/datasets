from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import Config

CARD_HEADER = """---
license: other
language:
- es
pretty_name: IGN Spanish Earthquake Catalogue
tags:
- earthquakes
- seismology
- geospatial
- public-data
configs:
- config_name: earthquakes
  data_files:
  - split: train
    path: data/earthquakes/*.parquet
---
"""


def stage(config: Config) -> Path:
    quality_path = config.artifacts_dir / "quality.json"
    if not quality_path.exists():
        raise FileNotFoundError("Run analyze before stage")
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    if quality.get("status") != "pass":
        raise RuntimeError("Refusing to stage a dataset whose quality status is not pass")
    if config.staging_dir.exists():
        shutil.rmtree(config.staging_dir)
    data_target = config.staging_dir / "data" / "earthquakes"
    artifacts_target = config.staging_dir / "artifacts"
    data_target.mkdir(parents=True)
    artifacts_target.mkdir(parents=True)
    sources = sorted((config.processed_dir / "earthquakes").glob("*.parquet"))
    if not sources:
        raise FileNotFoundError("No processed Parquet files found")
    for source in sources:
        shutil.copy2(source, data_target / source.name)
    for source in sorted(config.artifacts_dir.glob("*.json")):
        shutil.copy2(source, artifacts_target / source.name)
    project_readme = Path(__file__).resolve().parents[2] / "README.md"
    body = project_readme.read_text(encoding="utf-8")
    (config.staging_dir / "README.md").write_text(CARD_HEADER + "\n" + body, encoding="utf-8")
    manifest = {
        "included": [
            "README.md",
            "UPLOAD_MANIFEST.json",
            "data/earthquakes/*.parquet",
            "artifacts/*.json",
        ],
        "excluded": ["data/raw", "source CSV", "credentials", "local caches"],
    }
    (config.staging_dir / "UPLOAD_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return config.staging_dir
