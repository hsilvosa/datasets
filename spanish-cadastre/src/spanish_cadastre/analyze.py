from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .config import Config
from .io_utils import atomic_json, sha256_file


def profile_table(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    files = sorted(directory.glob("*.parquet"))
    if not files:
        return {"row_count": 0, "file_count": 0, "compressed_bytes": 0}, {
            "row_count": 0,
            "null_required_values": 0,
            "checks_passed": True,
        }
    schema = pq.read_schema(files[0])
    required = [field.name for field in schema if not field.nullable]
    geospatial = "geometry" in schema.names
    columns = required + (["geometry", "bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y"] if geospatial else [])
    rows = 0
    null_required = 0
    null_geometry = 0
    bounds = [None, None, None, None]
    for path in files:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=100_000, columns=columns):
            data = batch.to_pydict()
            rows += batch.num_rows
            null_required += sum(
                value is None for column in required for value in data[column]
            )
            if geospatial:
                null_geometry += sum(value is None for value in data["geometry"])
                values = [
                    [value for value in data[column] if value is not None]
                    for column in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")
                ]
                candidates = [
                    min(values[0]) if values[0] else None,
                    min(values[1]) if values[1] else None,
                    max(values[2]) if values[2] else None,
                    max(values[3]) if values[3] else None,
                ]
                for index, candidate in enumerate(candidates):
                    if candidate is None:
                        continue
                    if bounds[index] is None:
                        bounds[index] = candidate
                    elif index < 2:
                        bounds[index] = min(bounds[index], candidate)
                    else:
                        bounds[index] = max(bounds[index], candidate)
    profile = {
        "row_count": rows,
        "file_count": len(files),
        "compressed_bytes": sum(path.stat().st_size for path in files),
    }
    if geospatial:
        profile.update({"null_geometry_rows": null_geometry, "wgs84_bounds": bounds})
    quality = {
        "row_count": rows,
        "null_required_values": null_required,
        "null_geometry_rows": null_geometry if geospatial else None,
        "checks_passed": null_required == 0 and (not geospatial or null_geometry == 0),
    }
    return profile, quality


def analyze(config: Config) -> dict[str, Any]:
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    profiles: dict[str, Any] = {}
    quality_tables: dict[str, Any] = {}
    schemas: dict[str, Any] = {}
    checksums: list[dict[str, Any]] = []
    for directory in sorted(path for path in config.processed_dir.iterdir() if path.is_dir()):
        name = directory.name
        profiles[name], quality_tables[name] = profile_table(directory)
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
        "dataset": "Spanish Cadastre INSPIRE",
        "generated_at": generated_at,
        "tables": profiles,
    }
    quality = {
        "generated_at": generated_at,
        "tables": quality_tables,
        "checks_passed": all(item["checks_passed"] for item in quality_tables.values()),
    }
    download_path = config.raw_dir / "download_summary.json"
    retrieval = json.loads(download_path.read_text(encoding="utf-8")) if download_path.exists() else None
    provenance = {
        "generated_at": generated_at,
        "publisher": "Directorate-General for Cadastre, Spain",
        "source": "https://www.catastro.hacienda.gob.es/webinspire/index.html",
        "retrieval": retrieval,
        "configuration": config.public_dict(),
        "normalization": {
            "geometry": "Source INSPIRE geometries transformed to EPSG:4326 and encoded as WKB",
            "source_archives_published": False,
            "transformation": "GML features normalized into relational GeoParquet tables",
            "splits": "All rows are in train; geographic splits are left to downstream users",
        },
    }
    atomic_json(config.artifacts_dir / "profile.json", profile)
    atomic_json(config.artifacts_dir / "quality.json", quality)
    atomic_json(config.artifacts_dir / "schema.json", schemas)
    atomic_json(config.artifacts_dir / "provenance.json", provenance)
    atomic_json(config.artifacts_dir / "checksums.json", {"files": checksums})
    return profile
