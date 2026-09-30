from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.dataset as ds

from .config import Config
from .derive import (
    ALL_TABLES,
    BASE_LEGISLACION,
    BASE_SUMARIO,
    BASE_TEXTO,
    SCHEMAS,
    TABLE_BLOQUES,
    TABLE_DOCUMENTO,
    TABLE_ELI,
    TABLE_VERSIONES,
)
from .io_utils import atomic_json, read_json, sha256

DISTINCT_CAP = 3000
COUNTS_CAP = 3000


class ColumnProfile:
    def __init__(self, name: str, type_name: str) -> None:
        self.name = name
        self.type_name = type_name
        self.total = 0
        self.nulls = 0
        self.distinct: set[Any] = set()
        self.distinct_overflow = False
        self.counts: Counter[Any] = Counter()
        self.counts_overflow = False
        self.numeric_min: float | None = None
        self.numeric_max: float | None = None
        self.numeric_sum = 0.0
        self.numeric_count = 0
        self.str_min: int | None = None
        self.str_max: int | None = None
        self.str_sum = 0
        self.str_count = 0

    def add(self, values: list[Any]) -> None:
        for value in values:
            self.total += 1
            if value is None:
                self.nulls += 1
                continue
            if isinstance(value, float) and math.isnan(value):
                self.nulls += 1
                continue
            if not self.distinct_overflow:
                try:
                    self.distinct.add(value)
                except TypeError:
                    self.distinct_overflow = True
                if len(self.distinct) > DISTINCT_CAP:
                    self.distinct_overflow = True
                    self.distinct = set()
            if not self.counts_overflow and isinstance(value, (str, int, float, bool)):
                self.counts[value] += 1
                if len(self.counts) > COUNTS_CAP:
                    self.counts_overflow = True
                    self.counts = Counter()
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                number = float(value)
                self.numeric_min = number if self.numeric_min is None else min(self.numeric_min, number)
                self.numeric_max = number if self.numeric_max is None else max(self.numeric_max, number)
                self.numeric_sum += number
                self.numeric_count += 1
            if isinstance(value, str):
                length = len(value)
                self.str_min = length if self.str_min is None else min(self.str_min, length)
                self.str_max = length if self.str_max is None else max(self.str_max, length)
                self.str_sum += length
                self.str_count += 1

    def result(self) -> dict[str, Any]:
        present = self.total - self.nulls
        result: dict[str, Any] = {
            "type": self.type_name,
            "null_count": self.nulls,
            "null_fraction": round(self.nulls / self.total, 8) if self.total else 0,
            "distinct_count": None if self.distinct_overflow else len(self.distinct),
            "distinct_overflow": self.distinct_overflow,
            "top_values": (
                []
                if self.counts_overflow
                else [{"value": key, "count": count} for key, count in self.counts.most_common(20)]
            ),
        }
        if self.numeric_count and self.numeric_count == present:
            result["numeric"] = {
                "min": self.numeric_min,
                "max": self.numeric_max,
                "mean": self.numeric_sum / self.numeric_count,
            }
        if self.str_count and self.str_count == present:
            result["string_length"] = {
                "min": self.str_min,
                "max": self.str_max,
                "mean": self.str_sum / self.str_count,
            }
        return result


def _count_rows(directory: Path) -> int:
    if not directory.exists() or not any(directory.glob("*.parquet")):
        return 0
    return ds.dataset(directory, format="parquet").count_rows()


def _profile_table(config: Config, table: str) -> dict[str, Any]:
    directory = config.processed_dir / table
    files = sorted(directory.glob("*.parquet")) if directory.exists() else []
    if not files:
        return {"row_count": 0, "column_count": 0, "compressed_bytes": 0, "files": 0, "columns": {}}
    dataset = ds.dataset(directory, format="parquet")
    profiles = {field.name: ColumnProfile(field.name, str(field.type)) for field in dataset.schema}
    row_count = 0
    for batch in dataset.to_batches(batch_size=20_000):
        row_count += batch.num_rows
        for name, column in batch.to_pydict().items():
            profiles[name].add(column)
    return {
        "row_count": row_count,
        "column_count": len(dataset.schema),
        "compressed_bytes": sum(path.stat().st_size for path in files),
        "files": len(files),
        "columns": {name: profile.result() for name, profile in profiles.items()},
    }


def coverage(config: Config) -> dict[str, int]:
    base_norms = _count_rows(config.base_table_dir(BASE_LEGISLACION))
    base_texto = _count_rows(config.base_table_dir(BASE_TEXTO))
    base_documentos = _count_rows(config.base_table_dir(BASE_SUMARIO))
    return {
        "base_norms": base_norms,
        "base_texto_documents": base_texto,
        "base_sumario_documents": base_documentos,
        "bloques_rows": _count_rows(config.processed_dir / TABLE_BLOQUES),
        "versiones_rows": _count_rows(config.processed_dir / TABLE_VERSIONES),
        "eli_rows": _count_rows(config.processed_dir / TABLE_ELI),
        "documento_rows": _count_rows(config.processed_dir / TABLE_DOCUMENTO),
    }


def run_analyze(config: Config) -> dict[str, Any]:
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    profiles: dict[str, Any] = {}
    total_rows = 0
    total_bytes = 0
    for table in ALL_TABLES:
        profile = _profile_table(config, table)
        profiles[table] = profile
        total_rows += profile["row_count"]
        total_bytes += profile["compressed_bytes"]

    counts = coverage(config)
    schema = {
        "tables": {
            table: [
                {"name": field.name, "type": str(field.type), "nullable": field.nullable}
                for field in SCHEMAS[table]
            ]
            for table in ALL_TABLES
        }
    }

    gaps: list[str] = []
    if counts["bloques_rows"] == 0:
        gaps.append("legislacion_bloques is empty")
    if counts["eli_rows"] < counts["base_norms"]:
        gaps.append(f"legislacion_eli={counts['eli_rows']}/{counts['base_norms']}")
    if counts["bloques_rows"] < counts["base_texto_documents"]:
        gaps.append(f"legislacion_bloques={counts['bloques_rows']}/<base texto {counts['base_texto_documents']}")
    if counts["versiones_rows"] < counts["base_texto_documents"]:
        gaps.append(f"legislacion_versiones={counts['versiones_rows']}/<base texto {counts['base_texto_documents']}")
    unmatched = max(0, counts["base_norms"] - counts["documento_rows"])
    below_expected = config.expected_min_rows is not None and total_rows < config.expected_min_rows
    if below_expected:
        gaps.append(f"total_rows={total_rows} < expected_min_rows={config.expected_min_rows}")

    status = "pass" if not gaps else "fail"
    profile = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": "BOE and BORME detailed (derived)",
        "base_dataset": config.base_dataset,
        "total_rows": total_rows,
        "compressed_bytes": total_bytes,
        "tables": profiles,
    }
    quality = {
        "status": status,
        "gaps": gaps,
        "total_rows": total_rows,
        "expected_min_rows": config.expected_min_rows,
        "below_expected_minimum": below_expected,
        "coverage": {**counts, "documento_unmatched_norms": unmatched},
        "tables": {
            table: {
                "row_count": profiles[table]["row_count"],
                "compressed_bytes": profiles[table]["compressed_bytes"],
                "files": profiles[table]["files"],
            }
            for table in profiles
        },
    }
    derive_state = config.state_dir / "last_derive.json"
    provenance = {
        "dataset": "BOE and BORME detailed (derived)",
        "publisher": "Agencia Estatal Boletin Oficial del Estado (AEBOE)",
        "base_dataset": config.base_dataset,
        "source_url": "https://huggingface.co/datasets/hsilvosa/boe-borme",
        "license": "other",
        "derivation": "Block- and version-level extraction from consolidated legislation text",
        "derive_state": read_json(derive_state) if derive_state.exists() else {},
        "split_policy": "All rows are in train; derived from the base release",
        "append_only": True,
    }
    checksums = {
        "files": [
            {
                "path": str(path.relative_to(config.processed_dir)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for table in ALL_TABLES
            for path in sorted((config.processed_dir / table).glob("*.parquet"))
        ]
    }
    atomic_json(config.artifacts_dir / "profile.json", profile)
    atomic_json(config.artifacts_dir / "schema.json", schema)
    atomic_json(config.artifacts_dir / "quality.json", quality)
    atomic_json(config.artifacts_dir / "provenance.json", provenance)
    atomic_json(config.artifacts_dir / "checksums.json", checksums)
    return profile
