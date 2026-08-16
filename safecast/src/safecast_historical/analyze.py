from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from .config import Config
from .io_utils import atomic_json, sha256_file


def column_stats(files: list[Path], column: str) -> tuple[object | None, object | None, int]:
    minimum = None
    maximum = None
    nulls = 0
    for path in files:
        parquet = pq.ParquetFile(path)
        index = parquet.schema_arrow.get_field_index(column)
        for group_index in range(parquet.metadata.num_row_groups):
            stats = parquet.metadata.row_group(group_index).column(index).statistics
            if stats is None:
                continue
            nulls += stats.null_count
            if stats.has_min_max:
                minimum = stats.min if minimum is None else min(minimum, stats.min)
                maximum = stats.max if maximum is None else max(maximum, stats.max)
    return minimum, maximum, nulls


def analyze(config: Config) -> dict:
    files = sorted((config.processed_dir / "measurements").glob("*.parquet"))
    if not files:
        raise FileNotFoundError("No measurement Parquet files")
    rows = sum(pq.ParquetFile(path).metadata.num_rows for path in files)
    captured_min, captured_max, captured_nulls = column_stats(files, "captured_at")
    latitude_min, latitude_max, latitude_nulls = column_stats(files, "latitude")
    longitude_min, longitude_max, longitude_nulls = column_stats(files, "longitude")
    generated = datetime.now(UTC)
    generated_at = generated.isoformat()
    dataset = ds.dataset(config.processed_dir / "measurements", format="parquet")
    captured = ds.field("captured_at")
    before_1900 = dataset.count_rows(
        filter=captured < pa.scalar(-2_208_988_800_000_000, type=pa.timestamp("us"))
    )
    after_snapshot = dataset.count_rows(
        filter=captured
        > pa.scalar(
            generated.replace(tzinfo=None) + timedelta(days=1),
            type=pa.timestamp("us"),
        )
    )
    profile = {
        "dataset": "Safecast Historical Radiation Measurements",
        "generated_at": generated_at,
        "rows": rows,
        "parquet_files": len(files),
        "compressed_bytes": sum(path.stat().st_size for path in files),
        "captured_at": [str(captured_min), str(captured_max)],
        "latitude": [latitude_min, latitude_max],
        "longitude": [longitude_min, longitude_max],
    }
    quality = {
        "generated_at": generated_at,
        "null_captured_at": captured_nulls,
        "null_latitude": latitude_nulls,
        "null_longitude": longitude_nulls,
        "captured_before_1900": before_1900,
        "captured_after_snapshot": after_snapshot,
        "coordinates_in_range": latitude_min >= -90
        and latitude_max <= 90
        and longitude_min >= -180
        and longitude_max <= 180,
    }
    quality["source_anomalies_present"] = (
        captured_nulls + latitude_nulls + longitude_nulls + before_1900 + after_snapshot > 0
    )
    quality["checks_passed"] = quality["coordinates_in_range"]
    checksums = [
        {
            "file": path.relative_to(config.processed_dir).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in files
    ]
    provenance = {
        "generated_at": generated_at,
        "publisher": "Safecast",
        "source_url": "https://api.safecast.org/system/measurements.tar.gz",
        "source_archive_bytes": config.archive_path.stat().st_size,
        "source_archive_sha256": sha256_file(config.archive_path),
        "license": "CC0-1.0",
        "configuration": config.public_dict(),
    }
    atomic_json(config.artifacts_dir / "profile.json", profile)
    atomic_json(config.artifacts_dir / "quality.json", quality)
    atomic_json(config.artifacts_dir / "checksums.json", {"files": checksums})
    atomic_json(config.artifacts_dir / "provenance.json", provenance)
    atomic_json(
        config.artifacts_dir / "schema.json",
        [{"name": field.name, "type": str(field.type), "nullable": field.nullable} for field in pq.read_schema(files[0])],
    )
    return profile
