from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import Config

CARD_HEADER = """---
license: other
language:
- es
- pt
- en
pretty_name: OMIE Iberian Electricity Market Marginal Prices
tags:
- energy
- electricity
- reinforcement-learning
- time-series
- spain
- portugal
- omie
- public-data
configs:
- config_name: marginal_prices
  data_files:
  - split: train
    path: data/*.parquet
---
"""


def stage(config: Config) -> Path:
    """Prepare a staging directory ready for Hugging Face Dataset Hub upload."""
    if config.staging_dir.exists():
        shutil.rmtree(config.staging_dir)

    data_target = config.staging_dir / "data"
    artifacts_target = config.staging_dir / "artifacts"
    data_target.mkdir(parents=True)
    artifacts_target.mkdir(parents=True)

    sources = sorted(config.processed_dir.glob("*.parquet"))
    if not sources:
        raise FileNotFoundError("No processed Parquet files found. Run normalize first.")

    for source in sources:
        shutil.copy2(source, data_target / source.name)

    for source in sorted(config.artifacts_dir.glob("*.json")):
        shutil.copy2(source, artifacts_target / source.name)

    project_readme = Path(__file__).resolve().parents[2] / "README.md"
    body = project_readme.read_text(encoding="utf-8") if project_readme.exists() else "# OMIE Iberian Electricity Market"
    card = CARD_HEADER + "\n" + body
    (config.staging_dir / "README.md").write_text(card, encoding="utf-8")

    manifest = {
        "included": [
            "README.md",
            "UPLOAD_MANIFEST.json",
            "data/*.parquet",
            "artifacts/*.json",
        ],
        "excluded": ["data/raw", "temporary downloads", "credentials"],
    }
    (config.staging_dir / "UPLOAD_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return config.staging_dir


def publish(config: Config, repo_id: str, token: str | None = None) -> None:
    from huggingface_hub import HfApi

    staging = stage(config)
    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=staging,
        commit_message="Publish OMIE Iberian electricity market marginal prices snapshot",
    )
