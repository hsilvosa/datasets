from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import Config
from .io_utils import sha256

CARD_TEMPLATE = """---
license: other
language:
- es
pretty_name: "BOE and BORME Open Data (Spanish Official Gazette and Commercial Registry)"
tags:
- boe
- borme
- legislation
- legal
- public-data
- spain
- spanish
configs:
{configs}---
"""


def _tables(config: Config) -> list[str]:
    tables: list[str] = []
    if config.include_boe_sumario:
        tables.append("boe_sumario")
    if config.include_borme_sumario:
        tables.append("borme_sumario")
    if config.include_legislacion:
        tables.extend(
            ["boe_legislacion", "boe_legislacion_materias", "boe_legislacion_referencias"]
        )
        if config.include_legislacion_texto:
            tables.append("boe_legislacion_texto")
    if config.include_aux:
        tables.append("boe_aux")
    return tables


def _card_header(config: Config) -> str:
    lines = []
    for table in _tables(config):
        lines.append(f"- config_name: {table}")
        lines.append("  data_files:")
        lines.append("  - split: train")
        lines.append(f"    path: data/{table}/*.parquet")
    return CARD_TEMPLATE.format(configs="\n".join(lines) + "\n")


def _sha256(path: Path) -> str:
    return sha256(path)


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
    for table in _tables(config):
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
                    "sha256": _sha256(target),
                }
            )
    for source in sorted(config.artifacts_dir.glob("*.json")):
        target = artifacts_target / source.name
        shutil.copy2(source, target)
        included.append(
            {
                "path": str(target.relative_to(config.staging_dir)).replace("\\", "/"),
                "bytes": target.stat().st_size,
                "sha256": _sha256(target),
            }
        )
    project_readme = Path(__file__).resolve().parents[2] / "Readme.md"
    body = project_readme.read_text(encoding="utf-8")
    (config.staging_dir / "README.md").write_text(
        _card_header(config) + "\n" + body, encoding="utf-8"
    )
    manifest = {
        "dataset": "BOE and BORME open data",
        "end_date": config.resolved_end_date,
        "tables": _tables(config),
        "files": included,
        "excluded": ["data/raw", "state", "credentials", "local caches", "virtualenv"],
    }
    (config.staging_dir / "UPLOAD_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return config.staging_dir


def source_credits() -> dict[str, str]:
    return {
        "publisher": "Agencia Estatal Boletin Oficial del Estado (AEBOE)",
        "url": "https://www.boe.es/datosabiertos/api/api.php",
        "note": "BOE and BORME sumarios and consolidated legislation; reuse subject to the AEBOE legal notice.",
    }


__all__ = ["source_credits", "stage"]
