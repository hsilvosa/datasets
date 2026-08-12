from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .config import Config
from .io_utils import atomic_json, sha256_file


def _profile_table(directory: Path, dataset: str) -> tuple[dict[str, Any], dict[str, Any]]:
    files = sorted(directory.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No Parquet files found for {dataset}")
    value_column = "price" if dataset == "day_ahead_prices" else "load"
    rows = 0
    value_count = 0
    value_sum = 0.0
    value_sumsq = 0.0
    value_min: float | None = None
    value_max: float | None = None
    timestamp_min = None
    timestamp_max = None
    null_record_ids = 0
    null_timestamps = 0
    invalid_load_rows = 0
    zones: Counter[str] = Counter()
    countries: Counter[str] = Counter()
    resolutions: Counter[str] = Counter()
    units: Counter[str] = Counter()
    currencies: Counter[str] = Counter()
    columns = [
        "record_id",
        "timestamp_utc",
        "zone_key",
        "country_code",
        value_column,
        "resolution",
        "unit",
    ]
    if dataset == "day_ahead_prices":
        columns.append("currency")
    for path in files:
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=100_000, columns=columns):
            data = batch.to_pydict()
            count = batch.num_rows
            rows += count
            null_record_ids += sum(value is None for value in data["record_id"])
            null_timestamps += sum(value is None for value in data["timestamp_utc"])
            zones.update(value for value in data["zone_key"] if value is not None)
            countries.update(value for value in data["country_code"] if value is not None)
            resolutions.update(value for value in data["resolution"] if value is not None)
            units.update(value for value in data["unit"] if value is not None)
            if dataset == "day_ahead_prices":
                currencies.update(value for value in data["currency"] if value is not None)
            timestamps = [value for value in data["timestamp_utc"] if value is not None]
            if timestamps:
                batch_min, batch_max = min(timestamps), max(timestamps)
                timestamp_min = batch_min if timestamp_min is None else min(timestamp_min, batch_min)
                timestamp_max = batch_max if timestamp_max is None else max(timestamp_max, batch_max)
            for value in data[value_column]:
                if value is None or not math.isfinite(value):
                    continue
                number = float(value)
                value_count += 1
                value_sum += number
                value_sumsq += number * number
                value_min = number if value_min is None else min(value_min, number)
                value_max = number if value_max is None else max(value_max, number)
                if dataset == "actual_load" and number < 0:
                    invalid_load_rows += 1
    mean = value_sum / value_count if value_count else None
    variance = max(0.0, value_sumsq / value_count - mean * mean) if mean is not None else None
    profile = {
        "row_count": rows,
        "file_count": len(files),
        "compressed_bytes": sum(path.stat().st_size for path in files),
        "timestamp_min_utc": timestamp_min.isoformat() if timestamp_min else None,
        "timestamp_max_utc": timestamp_max.isoformat() if timestamp_max else None,
        "zone_count": len(zones),
        "country_count": len(countries),
        "rows_by_zone": dict(zones.most_common()),
        "rows_by_country": dict(countries.most_common()),
        "resolutions": dict(resolutions.most_common()),
        "units": dict(units.most_common()),
        "currencies": dict(currencies.most_common()),
        "numeric": {
            "column": value_column,
            "non_null_count": value_count,
            "null_count": rows - value_count,
            "min": value_min,
            "max": value_max,
            "mean": mean,
            "standard_deviation": math.sqrt(variance) if variance is not None else None,
        },
    }
    quality = {
        "row_count": rows,
        "null_record_ids": null_record_ids,
        "null_timestamps": null_timestamps,
        "null_values": rows - value_count,
        "negative_load_rows": invalid_load_rows,
        "checks_passed": null_record_ids == 0
        and null_timestamps == 0
        and rows == value_count
        and invalid_load_rows == 0,
    }
    return profile, quality


def analyze(config: Config) -> dict[str, Any]:
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    profiles: dict[str, Any] = {}
    quality: dict[str, Any] = {}
    schema: dict[str, Any] = {}
    checksums: list[dict[str, Any]] = []
    normalization_path = config.processed_dir / "normalization_summary.json"
    normalization = (
        json.loads(normalization_path.read_text(encoding="utf-8"))
        if normalization_path.exists()
        else {}
    )
    for dataset in config.datasets:
        directory = config.processed_dir / dataset
        profiles[dataset], quality[dataset] = _profile_table(directory, dataset)
        quality[dataset]["duplicate_rows_removed"] = normalization.get(dataset, {}).get(
            "duplicate_rows_removed", 0
        )
        quality[dataset]["out_of_range_rows_removed"] = normalization.get(dataset, {}).get(
            "out_of_range_rows_removed", 0
        )
        first = next(iter(sorted(directory.glob("*.parquet"))))
        arrow_schema = pq.read_schema(first)
        schema[dataset] = [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in arrow_schema
        ]
        for path in sorted(directory.glob("*.parquet")):
            checksums.append(
                {
                    "file": path.relative_to(config.processed_dir).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    summary_path = config.raw_dir / "download_summary.json"
    download_summary = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    )
    generated_at = datetime.now(UTC).isoformat()
    profile_document = {
        "dataset": "ENTSO-E Transparency prices and load",
        "generated_at": generated_at,
        "tables": profiles,
    }
    quality_document = {
        "generated_at": generated_at,
        "tables": quality,
        "checks_passed": all(item["checks_passed"] for item in quality.values()),
    }
    provenance = {
        "generated_at": generated_at,
        "publisher": "European Network of Transmission System Operators for Electricity (ENTSO-E)",
        "source": "https://transparency.entsoe.eu/",
        "api": config.base_url,
        "retrieval": download_summary,
        "configuration": config.public_dict(),
        "normalization": {
            "timestamps": "UTC instants derived from Period start, resolution, and Point position",
            "splits": "All observations are in train; downstream temporal splits are recommended",
            "missing_values": "Source gaps are preserved and are not imputed",
        },
    }
    atomic_json(config.artifacts_dir / "profile.json", profile_document)
    atomic_json(config.artifacts_dir / "quality.json", quality_document)
    atomic_json(config.artifacts_dir / "schema.json", schema)
    atomic_json(config.artifacts_dir / "provenance.json", provenance)
    atomic_json(config.artifacts_dir / "checksums.json", {"files": checksums})
    return profile_document
