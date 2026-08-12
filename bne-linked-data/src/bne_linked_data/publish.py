from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import Config

CARD_HEADER = """---
license: cc0-1.0
language:
- es
pretty_name: BNE Linked Data
tags:
- libraries
- linked-data
- rdf
- knowledge-graph
- spain
- public-data
configs:
{configs}
---
"""


def _config_yaml(names: list[str]) -> str:
    lines: list[str] = []
    for name in names:
        lines.extend(
            [
                f"- config_name: {name}",
                "  data_files:",
                "  - split: train",
                f"    path: data/{name}/*.parquet",
            ]
        )
    return "\n".join(lines)


def stage(config: Config) -> Path:
    if config.staging_dir.exists():
        shutil.rmtree(config.staging_dir)
    data_target = config.staging_dir / "data"
    artifacts_target = config.staging_dir / "artifacts"
    data_target.mkdir(parents=True)
    artifacts_target.mkdir(parents=True)
    names: list[str] = []
    for collection in config.collections:
        sources = sorted(config.processed_path(collection).glob("*.parquet"))
        if not sources:
            continue
        names.append(collection.name)
        target = data_target / collection.name
        target.mkdir()
        for source in sources:
            shutil.copy2(source, target / source.name)
    if not names:
        raise FileNotFoundError("No processed collections are available for staging")
    for source in sorted(config.artifacts_dir.glob("*.json")):
        shutil.copy2(source, artifacts_target / source.name)
    dataset_card = config.project_root / "DATASET_CARD.md"
    if not dataset_card.exists():
        raise FileNotFoundError(f"Missing Hugging Face dataset card: {dataset_card}")
    card = CARD_HEADER.format(configs=_config_yaml(names))
    card += "\n" + dataset_card.read_text(encoding="utf-8")
    (config.staging_dir / "README.md").write_text(card, encoding="utf-8")
    manifest = {
        "included": [
            "README.md",
            "UPLOAD_MANIFEST.json",
            "data/*/*.parquet",
            "artifacts/*.json",
        ],
        "excluded": ["data/raw", "BZip2 RDF dumps", "partial downloads", "local caches"],
    }
    (config.staging_dir / "UPLOAD_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return config.staging_dir


def upload(config: Config, repo_id: str) -> None:
    from huggingface_hub import HfApi

    staging = stage(config)
    api = HfApi()
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=staging,
        commit_message="Publish BNE Linked Data snapshot",
    )
