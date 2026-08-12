from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from .config import Config
from .io_utils import atomic_json, sha256


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


class ColumnProfile:
    def __init__(self, type_name: str) -> None:
        self.type_name = type_name
        self.total = 0
        self.nulls = 0
        self.distinct: set[str] = set()
        self.counts: Counter[str] = Counter()
        self.numeric_values: list[float] = []
        self.string_lengths: list[int] = []

    def add(self, values: list[Any]) -> None:
        for raw in values:
            self.total += 1
            if raw is None:
                self.nulls += 1
                continue
            value = _json_value(raw)
            key = json.dumps(value, ensure_ascii=False, sort_keys=True)
            self.distinct.add(key)
            self.counts[key] += 1
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.numeric_values.append(float(value))
            if isinstance(value, str):
                self.string_lengths.append(len(value))

    def result(self) -> dict[str, Any]:
        present = self.total - self.nulls
        result: dict[str, Any] = {
            "type": self.type_name,
            "null_count": self.nulls,
            "null_fraction": round(self.nulls / self.total, 8) if self.total else 0,
            "distinct_count": len(self.distinct),
            "top_values": [
                {"value": json.loads(value), "count": count}
                for value, count in self.counts.most_common(20)
            ],
        }
        if self.numeric_values and len(self.numeric_values) == present:
            result["numeric"] = {
                "min": min(self.numeric_values),
                "max": max(self.numeric_values),
                "mean": sum(self.numeric_values) / len(self.numeric_values),
            }
        if self.string_lengths and len(self.string_lengths) == present:
            result["string_length"] = {
                "min": min(self.string_lengths),
                "max": max(self.string_lengths),
                "mean": sum(self.string_lengths) / len(self.string_lengths),
            }
        return result


def analyze(config: Config) -> dict[str, Any]:
    import pyarrow.dataset as ds

    table_dir = config.processed_dir / "earthquakes"
    files = sorted(table_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"Run normalize first: {table_dir}")
    dataset = ds.dataset(table_dir, format="parquet")
    profiles = {field.name: ColumnProfile(str(field.type)) for field in dataset.schema}
    row_count = 0
    event_ids: set[str] = set()
    duplicate_ids = 0
    invalid_coordinates = 0
    negative_depths = 0
    country_counts: Counter[str] = Counter()
    for batch in dataset.to_batches(batch_size=10_000):
        row_count += batch.num_rows
        values_by_name = batch.to_pydict()
        for name, values in values_by_name.items():
            profiles[name].add(values)
        for identifier in values_by_name["event_id"]:
            if identifier in event_ids:
                duplicate_ids += 1
            event_ids.add(identifier)
        for latitude, longitude in zip(
            values_by_name["latitude"], values_by_name["longitude"], strict=True
        ):
            if (
                latitude is None
                or longitude is None
                or not (-90 <= latitude <= 90)
                or not (-180 <= longitude <= 180)
            ):
                invalid_coordinates += 1
        negative_depths += sum(
            depth is not None and depth < 0 for depth in values_by_name["depth_km"]
        )
        country_counts.update(
            country or "unassigned" for country in values_by_name["country_code"]
        )
    compressed_bytes = sum(path.stat().st_size for path in files)
    profile = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": "IGN Earthquakes",
        "tables": {
            "earthquakes": {
                "row_count": row_count,
                "column_count": len(dataset.schema),
                "compressed_bytes": compressed_bytes,
                "columns": {name: item.result() for name, item in profiles.items()},
            }
        },
        "geography": {
            "classification_method": (
                "Derived from the country, province, or island suffix in the IGN "
                "location text; locations without a suffix remain unassigned"
            ),
            "country_counts": dict(country_counts.most_common()),
        },
    }
    schema = {
        "tables": {
            "earthquakes": [
                {"name": field.name, "type": str(field.type), "nullable": field.nullable}
                for field in dataset.schema
            ]
        }
    }
    below_expected = (
        config.expected_min_rows is not None and row_count < config.expected_min_rows
    )
    status = (
        "pass"
        if not duplicate_ids and not invalid_coordinates and not below_expected
        else "fail"
    )
    quality = {
        "status": status,
        "tables": {
            "earthquakes": {
                "row_count": row_count,
                "duplicate_primary_keys": duplicate_ids,
                "invalid_coordinates": invalid_coordinates,
                "negative_depths": negative_depths,
                "expected_min_rows": config.expected_min_rows,
                "below_expected_minimum": below_expected,
                "country_assigned_rows": row_count - country_counts["unassigned"],
                "country_unassigned_rows": country_counts["unassigned"],
            }
        },
    }
    raw_provenance_path = config.raw_dir / "provenance.json"
    raw_provenance = json.loads(raw_provenance_path.read_text(encoding="utf-8"))
    provenance = {
        **raw_provenance,
        "dataset": "IGN Earthquakes",
        "publisher": "Instituto Geografico Nacional (IGN)",
        "citation": "Instituto Geografico Nacional (IGN). Catalogo de terremotos.",
        "raw_responses_published": False,
        "normalization": {
            "format": "Parquet",
            "compression": "zstd",
            "timezone": "UTC",
            "split_policy": "All rows are in train; temporal splits are left to downstream users",
            "html_fallback_files": config.html_fallback_files or [],
        },
    }
    checksums = {
        "files": [
            {
                "path": str(path.relative_to(config.processed_dir)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        ]
    }
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(config.artifacts_dir / "profile.json", profile)
    atomic_json(config.artifacts_dir / "schema.json", schema)
    atomic_json(config.artifacts_dir / "quality.json", quality)
    atomic_json(config.artifacts_dir / "provenance.json", provenance)
    atomic_json(config.artifacts_dir / "checksums.json", checksums)
    return profile
