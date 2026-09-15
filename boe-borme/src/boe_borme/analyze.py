from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow.dataset as ds

from . import layout
from .config import Config
from .io_utils import atomic_json, sha256
from .normalize import ALL_TABLES, SCHEMAS

DISTINCT_CAP = 5000
COUNTS_CAP = 5000


class ColumnProfile:
    def __init__(self, name: str, type_name: str, track_distinct: bool = True) -> None:
        self.name = name
        self.type_name = type_name
        self.track_distinct = track_distinct
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
            if self.track_distinct and not self.distinct_overflow:
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
                numeric = float(value)
                self.numeric_min = numeric if self.numeric_min is None else min(self.numeric_min, numeric)
                self.numeric_max = numeric if self.numeric_max is None else max(self.numeric_max, numeric)
                self.numeric_sum += numeric
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


def _table_dir(config: Config, table: str) -> Path:
    return config.processed_dir / table


def _enabled_tables(config: Config) -> list[str]:
    tables: list[str] = []
    if config.include_boe_sumario:
        tables.append("boe_sumario")
    if config.include_borme_sumario:
        tables.append("borme_sumario")
    if config.include_legislacion:
        tables.extend(["boe_legislacion", "boe_legislacion_materias", "boe_legislacion_referencias"])
        if config.include_legislacion_texto:
            tables.append("boe_legislacion_texto")
    if config.include_aux:
        tables.append("boe_aux")
    return [table for table in tables if table in ALL_TABLES]


def _profile_table(config: Config, table: str) -> dict[str, Any]:
    table_dir = _table_dir(config, table)
    files = sorted(table_dir.glob("*.parquet")) if table_dir.exists() else []
    if not files:
        return {"row_count": 0, "column_count": 0, "compressed_bytes": 0, "files": 0, "columns": {}}
    dataset = ds.dataset(table_dir, format="parquet")
    profiles = {
        field.name: ColumnProfile(field.name, str(field.type), track_distinct=not field.name.endswith("_xml"))
        for field in dataset.schema
    }
    row_count = 0
    for batch in dataset.to_batches(batch_size=20_000):
        row_count += batch.num_rows
        values = batch.to_pydict()
        for name, column in values.items():
            profiles[name].add(column)
    compressed_bytes = sum(path.stat().st_size for path in files)
    return {
        "row_count": row_count,
        "column_count": len(dataset.schema),
        "compressed_bytes": compressed_bytes,
        "files": len(files),
        "columns": {name: profile.result() for name, profile in profiles.items()},
    }


def _date_coverage(config: Config, dataset: str) -> dict[str, Any]:
    start = config.start_for(dataset)
    end = config.end()
    planned = (end - start).days + 1
    payloads, empties = layout.count_date_files(config.raw_dir, dataset)
    covered = payloads + empties
    return {
        "planned_days": planned,
        "payload_days": payloads,
        "empty_days": empties,
        "covered_days": covered,
        "gap_days": max(0, planned - covered),
    }


def _count_resolved(directory: Path, suffix: str, empty_suffix: str) -> tuple[int, int]:
    if not directory.exists():
        return 0, 0
    payloads = len([p for p in directory.glob(f"*/{suffix}")])
    empties = len([p for p in directory.glob(f"*/{empty_suffix}")])
    return payloads, empties


def _legislacion_coverage(config: Config) -> dict[str, Any]:
    catalog = layout.read_catalog(config.raw_dir)
    metadata, _ = _count_resolved(config.raw_dir / layout.BOE_LEGISLACION, "metadata.json", "metadata.empty.json")
    analisis, analisis_empty = _count_resolved(
        config.raw_dir / layout.BOE_LEGISLACION, "analisis.json", "analisis.empty.json"
    )
    texto, texto_empty = _count_resolved(
        config.raw_dir / layout.BOE_LEGISLACION_TEXTO, "texto.xml", "texto.empty.json"
    )
    return {
        "catalog_norms": len(catalog),
        "metadata_norms": metadata,
        "analisis_norms": analisis + analisis_empty,
        "texto_norms": texto + texto_empty,
        "texto_empty": texto_empty,
    }


def _aux_coverage(config: Config) -> dict[str, Any]:
    names = layout.AUX_TABLES
    resolved = [name for name in names if layout.is_aux_complete(config.raw_dir, name)]
    return {"planned": len(names), "resolved": len(resolved), "missing": sorted(set(names) - set(resolved))}


def run_analyze(config: Config) -> dict[str, Any]:
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    profiles: dict[str, Any] = {}
    total_rows = 0
    total_bytes = 0
    for table in _enabled_tables(config):
        profile = _profile_table(config, table)
        profiles[table] = profile
        total_rows += profile["row_count"]
        total_bytes += profile["compressed_bytes"]

    schema = {
        "tables": {
            table: [
                {"name": field.name, "type": str(field.type), "nullable": field.nullable}
                for field in SCHEMAS[table]
            ]
            for table in _enabled_tables(config)
        }
    }
    coverage: dict[str, Any] = {}
    if config.include_boe_sumario:
        coverage["boe_sumario"] = _date_coverage(config, layout.BOE_SUMARIO)
    if config.include_borme_sumario:
        coverage["borme_sumario"] = _date_coverage(config, layout.BORME_SUMARIO)
    if config.include_legislacion:
        coverage["boe_legislacion"] = _legislacion_coverage(config)
    if config.include_aux:
        coverage["boe_aux"] = _aux_coverage(config)

    gaps: list[str] = []
    if config.include_boe_sumario and coverage["boe_sumario"]["gap_days"] > 0:
        gaps.append(f"boe_sumario gap_days={coverage['boe_sumario']['gap_days']}")
    if config.include_borme_sumario and coverage["borme_sumario"]["gap_days"] > 0:
        gaps.append(f"borme_sumario gap_days={coverage['borme_sumario']['gap_days']}")
    if config.include_legislacion:
        leg = coverage["boe_legislacion"]
        if leg["catalog_norms"] == 0:
            gaps.append("boe_legislacion empty catalog")
        if leg["metadata_norms"] < leg["catalog_norms"]:
            gaps.append(f"boe_legislacion metadata={leg['metadata_norms']}/{leg['catalog_norms']}")
        if leg["analisis_norms"] < leg["catalog_norms"]:
            gaps.append(f"boe_legislacion analisis={leg['analisis_norms']}/{leg['catalog_norms']}")
        if config.include_legislacion_texto and leg["texto_norms"] < leg["catalog_norms"]:
            gaps.append(f"boe_legislacion texto={leg['texto_norms']}/{leg['catalog_norms']}")
    if config.include_aux and coverage["boe_aux"]["missing"]:
        gaps.append(f"boe_aux missing={coverage['boe_aux']['missing']}")
    below_expected = config.expected_min_rows is not None and total_rows < config.expected_min_rows
    if below_expected:
        gaps.append(f"total_rows={total_rows} < expected_min_rows={config.expected_min_rows}")

    status = "pass" if not gaps else "fail"
    profile = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": "BOE and BORME open data",
        "end_date": config.resolved_end_date,
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
        "coverage": coverage,
        "tables": {
            table: {
                "row_count": profiles[table]["row_count"],
                "compressed_bytes": profiles[table]["compressed_bytes"],
                "files": profiles[table]["files"],
            }
            for table in profiles
        },
    }
    raw_provenance = _read_provenance(config)
    provenance = {
        **raw_provenance,
        "dataset": "BOE and BORME open data",
        "publisher": "Agencia Estatal Boletin Oficial del Estado (AEBOE)",
        "source_url": f"{config.base_url}/datosabiertos/api/api.php",
        "citation": "Agencia Estatal Boletin Oficial del Estado. Datos abiertos (BOE y BORME).",
        "license": "other",
        "raw_responses_published": False,
        "normalization": {
            "format": "Parquet",
            "compression": "zstd",
            "timezone": "UTC",
            "split_policy": "All rows are in train; version history is retained, downstream deduplicates",
            "append_only": True,
        },
    }
    checksums = {
        "files": [
            {
                "path": str(path.relative_to(config.processed_dir)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for table in _enabled_tables(config)
            for path in sorted(_table_dir(config, table).glob("*.parquet"))
        ]
    }
    atomic_json(config.artifacts_dir / "profile.json", profile)
    atomic_json(config.artifacts_dir / "schema.json", schema)
    atomic_json(config.artifacts_dir / "quality.json", quality)
    atomic_json(config.artifacts_dir / "provenance.json", provenance)
    atomic_json(config.artifacts_dir / "checksums.json", checksums)
    return profile


def _read_provenance(config: Config) -> dict[str, Any]:
    times: list[str] = []
    for name in ("last_download.json", "last_normalize.json"):
        path = config.state_dir / name
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "started_at" in payload:
                times.append(str(payload["started_at"]))
            if "run_id" in payload:
                times.append(str(payload["run_id"]))
    return {"run_markers": times}


def coverage_summary(config: Config) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    if config.include_boe_sumario:
        coverage[layout.BOE_SUMARIO] = _date_coverage(config, layout.BOE_SUMARIO)
    if config.include_borme_sumario:
        coverage[layout.BORME_SUMARIO] = _date_coverage(config, layout.BORME_SUMARIO)
    if config.include_legislacion:
        coverage[layout.BOE_LEGISLACION] = _legislacion_coverage(config)
    if config.include_aux:
        coverage[layout.BOE_AUX] = _aux_coverage(config)
    return coverage


def today() -> date:
    return datetime.now(UTC).date()
