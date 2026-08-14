from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .config import Config

CARD_HEADER = """---
license: other
language:
- es
pretty_name: OpenPLACSP Historical Spanish Public Procurement
tags:
- public-procurement
- government
- spain
- time-series
- public-data
configs:
{configs}
---
"""


def config_yaml(names: list[str]) -> str:
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
    for directory in sorted(path for path in config.processed_dir.iterdir() if path.is_dir()):
        sources = sorted(directory.glob("*.parquet"))
        if not sources:
            continue
        names.append(directory.name)
        target = data_target / directory.name
        target.mkdir()
        for source in sources:
            shutil.copy2(source, target / source.name)
    for source in sorted(config.artifacts_dir.glob("*.json")):
        shutil.copy2(source, artifacts_target / source.name)
    dataset_card = Path(__file__).resolve().parents[2] / "DATASET_CARD.md"
    body = dataset_card.read_text(encoding="utf-8")
    (config.staging_dir / "README.md").write_text(
        CARD_HEADER.format(configs=config_yaml(names)) + "\n" + body,
        encoding="utf-8",
    )
    manifest = {
        "included": ["README.md", "UPLOAD_MANIFEST.json", "data/*/*.parquet", "artifacts/*.json"],
        "excluded": [
            "source ZIP archives",
            "ATOM XML",
            "documents linked by notices",
            "local caches",
        ],
    }
    (config.staging_dir / "UPLOAD_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return config.staging_dir


def upload(config: Config, repo_id: str) -> None:
    staging = stage(config)
    subprocess.run(
        [
            "hf",
            "upload",
            repo_id,
            str(staging),
            ".",
            "--type",
            "dataset",
            "--commit-message",
            "Publish OpenPLACSP historical snapshot",
        ],
        check=True,
    )
