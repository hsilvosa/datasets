from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import Config

CARD_HEADER = """---
license: other
language:
- es
pretty_name: AEMPS CIMA Research Dataset
tags:
- medicine
- public-data
- regulatory
- knowledge-graph
configs:
{configs}
---
"""


def _config_yaml(table_names: list[str]) -> str:
    lines = []
    for name in table_names:
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

    table_names = []
    for table_dir in sorted(path for path in config.processed_dir.iterdir() if path.is_dir()):
        files = sorted(table_dir.glob("*.parquet"))
        if not files:
            continue
        table_names.append(table_dir.name)
        target = data_target / table_dir.name
        target.mkdir()
        for source in files:
            shutil.copy2(source, target / source.name)
    for source in sorted(config.artifacts_dir.glob("*.json")):
        shutil.copy2(source, artifacts_target / source.name)

    project_readme = Path(__file__).resolve().parents[2] / "README.md"
    body = project_readme.read_text(encoding="utf-8")
    if body.startswith("---"):
        closing = body.find("---", 3)
        body = body[closing + 3 :].lstrip()
    card = CARD_HEADER.format(configs=_config_yaml(table_names)) + "\n" + body
    (config.staging_dir / "README.md").write_text(card, encoding="utf-8")
    manifest = {
        "included": [
            "README.md",
            "UPLOAD_MANIFEST.json",
            "data/*/*.parquet",
            "artifacts/*.json",
        ],
        "excluded": ["data/raw", "API responses", "credentials", "local caches"],
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
        commit_message="Publish reproducible AEMPS CIMA research snapshot",
    )
