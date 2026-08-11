from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from .config import Config
from .io_utils import atomic_json, sha256

DISTINCT_LIMIT = 100_000
TOP_VALUE_CANDIDATES = 10_000


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _display_value(value: Any, limit: int = 200) -> Any:
    value = _json_value(value)
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"... [truncated; {len(value)} characters]"
    return value


def _count_key(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(serialized) <= 512:
        return serialized
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return json.dumps({"sha256": digest, "preview": _display_value(value)}, ensure_ascii=False)


class _ColumnAccumulator:
    def __init__(self, type_name: str):
        self.type_name = type_name
        self.total = 0
        self.null_count = 0
        self.samples: list[Any] = []
        self.distinct: set[str] | None = set()
        self.distinct_lower_bound = 0
        self.counts: Counter[str] = Counter()
        self.numeric_count = 0
        self.numeric_sum = 0.0
        self.numeric_min: float | int | None = None
        self.numeric_max: float | int | None = None
        self.string_count = 0
        self.string_length_sum = 0
        self.string_length_min: int | None = None
        self.string_length_max: int | None = None

    def add_many(self, values: list[Any]) -> None:
        for raw_value in values:
            self.total += 1
            if raw_value is None:
                self.null_count += 1
                continue
            value = _json_value(raw_value)
            if len(self.samples) < 5:
                self.samples.append(_display_value(value))
            key = _count_key(value)
            if self.distinct is not None:
                self.distinct.add(key)
                if len(self.distinct) > DISTINCT_LIMIT:
                    self.distinct_lower_bound = len(self.distinct)
                    self.distinct = None
            if key in self.counts or len(self.counts) < TOP_VALUE_CANDIDATES:
                self.counts[key] += 1
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.numeric_count += 1
                self.numeric_sum += value
                self.numeric_min = value if self.numeric_min is None else min(self.numeric_min, value)
                self.numeric_max = value if self.numeric_max is None else max(self.numeric_max, value)
            if isinstance(value, str):
                length = len(value)
                self.string_count += 1
                self.string_length_sum += length
                self.string_length_min = (
                    length if self.string_length_min is None else min(self.string_length_min, length)
                )
                self.string_length_max = (
                    length if self.string_length_max is None else max(self.string_length_max, length)
                )

    def result(self) -> dict[str, Any]:
        present = self.total - self.null_count
        result: dict[str, Any] = {
            "type": self.type_name,
            "null_count": self.null_count,
            "null_fraction": round(self.null_count / self.total, 8) if self.total else 0,
            "distinct_count": len(self.distinct) if self.distinct is not None else None,
            "distinct_count_lower_bound": (
                None if self.distinct is not None else self.distinct_lower_bound
            ),
        }
        if present:
            result["sample_values"] = self.samples
            result["top_values"] = [
                {"value": json.loads(value), "count": count}
                for value, count in self.counts.most_common(20)
            ]
        if self.numeric_count == present and present:
            result["numeric"] = {
                "min": self.numeric_min,
                "max": self.numeric_max,
                "mean": self.numeric_sum / self.numeric_count,
            }
        if self.string_count == present and present:
            result["string_length"] = {
                "min": self.string_length_min,
                "max": self.string_length_max,
                "mean": self.string_length_sum / self.string_count,
            }
        return result


def analyze(config: Config) -> dict[str, Any]:
    import pyarrow.dataset as ds

    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    profile: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": "AEMPS CIMA",
        "tables": {},
    }
    schema: dict[str, Any] = {"tables": {}}
    quality: dict[str, Any] = {"status": "pass", "tables": {}}
    checksums: list[dict[str, Any]] = []

    for table_dir in sorted(path for path in config.processed_dir.iterdir() if path.is_dir()):
        files = sorted(table_dir.glob("*.parquet"))
        if not files:
            continue
        dataset = ds.dataset(table_dir, format="parquet")
        accumulators = {
            field.name: _ColumnAccumulator(str(field.type)) for field in dataset.schema
        }
        row_count = 0
        medication_identifiers: set[str] = set()
        duplicate_keys = 0
        for batch in dataset.to_batches(batch_size=10_000):
            row_count += batch.num_rows
            for field, column in zip(batch.schema, batch.columns, strict=True):
                values = column.to_pylist()
                accumulators[field.name].add_many(values)
                if field.name == "registration_number" and table_dir.name == "medications":
                    for identifier in values:
                        if identifier in medication_identifiers:
                            duplicate_keys += 1
                        else:
                            medication_identifiers.add(identifier)
        profile["tables"][table_dir.name] = {
            "row_count": row_count,
            "column_count": len(dataset.schema),
            "compressed_bytes": sum(path.stat().st_size for path in files),
            "columns": {name: accumulator.result() for name, accumulator in accumulators.items()},
        }
        schema["tables"][table_dir.name] = [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in dataset.schema
        ]
        if duplicate_keys:
            quality["status"] = "fail"
        quality["tables"][table_dir.name] = {
            "row_count": row_count,
            "duplicate_primary_keys": duplicate_keys,
        }
        for path in files:
            checksums.append(
                {
                    "path": str(path.relative_to(config.processed_dir)).replace("\\", "/"),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )

    snapshot_path = config.raw_dir / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else {}
    provenance = {
        "dataset": "AEMPS CIMA",
        "publisher": "Agencia Espanola de Medicamentos y Productos Sanitarios (AEMPS)",
        "source_homepage": "https://cima.aemps.es/cima/publico/home.html",
        "api_base_url": config.base_url,
        "api_documentation": "https://cima.aemps.es/cima/resources/docs/CIMA_REST_API.pdf",
        "open_data_statement": "https://sede.aemps.gob.es/datos-abiertos/",
        "retrieved_at": snapshot.get("retrieved_at"),
        "api_documentation_version": snapshot.get("api_documentation_version", "1.23"),
        "research_only": True,
        "raw_api_responses_published": False,
        "historical_change_events_included": False,
        "normalization": {
            "format": "Parquet",
            "compression": "zstd",
            "document_text": "HTML retained and plain text derived with HTML tags removed",
            "split_policy": "All rows are in train; no artificial benchmark split",
        },
    }
    atomic_json(config.artifacts_dir / "profile.json", profile)
    atomic_json(config.artifacts_dir / "schema.json", schema)
    atomic_json(config.artifacts_dir / "quality.json", quality)
    atomic_json(config.artifacts_dir / "provenance.json", provenance)
    atomic_json(config.artifacts_dir / "checksums.json", {"files": checksums})
    return profile
