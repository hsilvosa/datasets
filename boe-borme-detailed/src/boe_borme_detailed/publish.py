from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import Config
from .derive import ALL_TABLES
from .io_utils import sha256

CARD_TEMPLATE = """---
license: other
language:
- es
pretty_name: "BOE and BORME Detailed: Article-Level Consolidated Legislation"
tags:
- boe
- borme
- legislation
- legal
- public-data
- spain
- spanish
- legal-nlp
configs:
{configs}---
"""

SELF_REFERENCE_PREFIX = "Published dataset:"


def card_body(text: str) -> str:
    lines = [
        line for line in text.splitlines() if not line.strip().startswith(SELF_REFERENCE_PREFIX)
    ]
    return "\n".join(lines).strip("\n") + "\n"


def _card_header() -> str:
    lines = []
    for table in ALL_TABLES:
        lines.append(f"- config_name: {table}")
        lines.append("  data_files:")
        lines.append("  - split: train")
        lines.append(f"    path: data/{table}/*.parquet")
    return CARD_TEMPLATE.format(configs="\n".join(lines) + "\n")


def stage(config: Config) -> Path:
    quality_path = config.artifacts_dir / "quality.json"
    if not quality_path.exists():
        raise FileNotFoundError("Run analyze before stage")
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    if quality.get("status") != "pass":
        raise RuntimeError(
            "Refusing to stage a dataset whose quality status is not pass: "
            + "; ".join(quality.get("gaps", []))
        )
    if config.staging_dir.exists():
        shutil.rmtree(config.staging_dir)
    artifacts_target = config.staging_dir / "artifacts"
    artifacts_target.mkdir(parents=True)

    included: list[dict[str, object]] = []
    for table in ALL_TABLES:
        source_dir = config.processed_dir / table
        if not source_dir.exists():
            continue
        target_dir = config.staging_dir / "data" / table
        target_dir.mkdir(parents=True)
        for source in sorted(source_dir.glob("*.parquet")):
            target = target_dir / source.name
            shutil.copy2(source, target)
            included.append(
                {
                    "path": str(target.relative_to(config.staging_dir)).replace("\\", "/"),
                    "bytes": target.stat().st_size,
                    "sha256": sha256(target),
                }
            )
    for source in sorted(config.artifacts_dir.glob("*.json")):
        target = artifacts_target / source.name
        shutil.copy2(source, target)
        included.append(
            {
                "path": str(target.relative_to(config.staging_dir)).replace("\\", "/"),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )
    project_readme = Path(__file__).resolve().parents[2] / "Readme.md"
    body = card_body(project_readme.read_text(encoding="utf-8"))
    (config.staging_dir / "README.md").write_text(_card_header() + "\n" + body, encoding="utf-8")
    manifest = {
        "dataset": "BOE and BORME detailed (derived)",
        "base_dataset": config.base_dataset,
        "tables": list(ALL_TABLES),
        "files": included,
        "excluded": ["base release", "state", "credentials", "local caches", "virtualenv"],
    }
    (config.staging_dir / "UPLOAD_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return config.staging_dir
