from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .config import Config
from .io_utils import atomic_json, sha256_file


def profile_table(directory: Path, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    files = sorted(directory.glob("*.parquet"))
    if not files:
        return (
            {"row_count": 0, "file_count": 0, "compressed_bytes": 0},
            {"row_count": 0, "null_required_values": 0, "checks_passed": name != "versions"},
        )
    schema = pq.read_schema(files[0])
    required = [field.name for field in schema if not field.nullable]
    rows = 0
    null_required = 0
    status_counts: Counter[str] = Counter()
    deleted_rows = 0
    timestamp_min = None
    timestamp_max = None
    columns = sorted(
        set(required + (["status_code", "is_deleted", "updated_at"] if name == "versions" else []))
    )
    for path in files:
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=100_000, columns=columns):
            values = batch.to_pydict()
            rows += batch.num_rows
            for column in required:
                null_required += sum(value is None for value in values[column])
            if name == "versions":
                status_counts.update(value for value in values["status_code"] if value is not None)
                deleted_rows += sum(value is True for value in values["is_deleted"])
                timestamps = [value for value in values["updated_at"] if value is not None]
                if timestamps:
                    low, high = min(timestamps), max(timestamps)
                    timestamp_min = low if timestamp_min is None else min(timestamp_min, low)
                    timestamp_max = high if timestamp_max is None else max(timestamp_max, high)
    profile = {
        "row_count": rows,
        "file_count": len(files),
        "compressed_bytes": sum(path.stat().st_size for path in files),
    }
    if name == "versions":
        profile.update(
            {
                "updated_at_min": timestamp_min.isoformat() if timestamp_min else None,
                "updated_at_max": timestamp_max.isoformat() if timestamp_max else None,
                "deleted_rows": deleted_rows,
                "rows_by_status": dict(status_counts.most_common()),
            }
        )
    quality = {
        "row_count": rows,
        "null_required_values": null_required,
        "checks_passed": null_required == 0 and (rows > 0 if name == "versions" else True),
    }
    return profile, quality


def analyze(config: Config) -> dict[str, Any]:
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    tables: dict[str, Any] = {}
    quality_tables: dict[str, Any] = {}
    schemas: dict[str, Any] = {}
    checksums: list[dict[str, Any]] = []
    for directory in sorted(path for path in config.processed_dir.iterdir() if path.is_dir()):
        name = directory.name
        tables[name], quality_tables[name] = profile_table(directory, name)
        files = sorted(directory.glob("*.parquet"))
        if files:
            schemas[name] = [
                {"name": field.name, "type": str(field.type), "nullable": field.nullable}
                for field in pq.read_schema(files[0])
            ]
        for path in files:
            checksums.append(
                {
                    "file": path.relative_to(config.processed_dir).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    generated_at = datetime.now(UTC).isoformat()
    profile = {
        "dataset": "OpenPLACSP historical procurement",
        "generated_at": generated_at,
        "tables": tables,
    }
    quality = {
        "generated_at": generated_at,
        "tables": quality_tables,
        "checks_passed": all(item["checks_passed"] for item in quality_tables.values()),
    }
    summary_path = config.raw_dir / "download_summary.json"
    retrieval = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    )
    provenance = {
        "generated_at": generated_at,
        "publisher": "Direccion General del Patrimonio del Estado",
        "source": "https://www.hacienda.gob.es/es-ES/GobiernoAbierto/Datos%20Abiertos/Paginas/licitaciones_plataforma_contratacion.aspx",
        "retrieval": retrieval,
        "configuration": config.public_dict(),
        "normalization": {
            "history": "Every published update is retained as a separate version",
            "deletions": "ATOM deleted-entry records are retained",
            "documents": "Document URLs are metadata only; documents are not downloaded",
            "splits": "All rows use train; temporal splits are left to downstream users",
        },
    }
    atomic_json(config.artifacts_dir / "profile.json", profile)
    atomic_json(config.artifacts_dir / "quality.json", quality)
    atomic_json(config.artifacts_dir / "schema.json", schemas)
    atomic_json(config.artifacts_dir / "provenance.json", provenance)
    atomic_json(config.artifacts_dir / "checksums.json", {"files": checksums})
    return profile
