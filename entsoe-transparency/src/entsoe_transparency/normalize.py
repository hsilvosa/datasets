from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .config import Config, Zone
from .io_utils import atomic_json
from .tasks import build_tasks
from .xml_parser import parse_document

COMMON_FIELDS = [
    pa.field("record_id", pa.string(), nullable=False),
    pa.field("timestamp_utc", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("zone_key", pa.string(), nullable=False),
    pa.field("zone_name", pa.string(), nullable=False),
    pa.field("country_code", pa.string(), nullable=False),
    pa.field("eic_code", pa.string(), nullable=False),
]


def schema_for(dataset: str) -> pa.Schema:
    value_fields = (
        [pa.field("price", pa.float64(), nullable=False), pa.field("currency", pa.string())]
        if dataset == "day_ahead_prices"
        else [pa.field("load", pa.float64(), nullable=False)]
    )
    return pa.schema(
        COMMON_FIELDS
        + value_fields
        + [
            pa.field("unit", pa.string()),
            pa.field("resolution", pa.string()),
            pa.field("curve_type", pa.string()),
            pa.field("business_type", pa.string()),
            pa.field("contract_type", pa.string()),
            pa.field("auction_type", pa.string()),
            pa.field("classification_position", pa.int32()),
            pa.field("document_id", pa.string()),
            pa.field("revision_number", pa.int32()),
            pa.field("timeseries_id", pa.string()),
            pa.field("source_file", pa.string(), nullable=False),
        ]
    )


class ShardWriter:
    def __init__(self, directory: Path, schema: pa.Schema, rows_per_file: int):
        self.directory = directory
        self.schema = schema
        self.rows_per_file = rows_per_file
        self.buffer: list[dict[str, Any]] = []
        self.index = 0
        self.rows = 0
        self.files: list[Path] = []
        directory.mkdir(parents=True, exist_ok=True)

    def add(self, row: dict[str, Any]) -> None:
        self.buffer.append(row)
        if len(self.buffer) >= self.rows_per_file:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
        table = pa.Table.from_pylist(self.buffer, schema=self.schema)
        path = self.directory / f"train-{self.index:05d}.parquet"
        pq.write_table(table, path, compression="zstd", use_dictionary=True)
        self.files.append(path)
        self.rows += len(self.buffer)
        self.buffer.clear()
        self.index += 1


def _zone_lookup(config: Config) -> dict[str, Zone]:
    return {zone.key: zone for zone in config.zones()}


def normalize(config: Config) -> dict[str, object]:
    manifest_path = config.raw_dir / "download_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("Run the download stage before normalization")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks_by_id = {task.task_id: task for task in build_tasks(config)}
    zones = _zone_lookup(config)
    if config.processed_dir.exists():
        shutil.rmtree(config.processed_dir)
    results: dict[str, object] = {}
    for dataset in config.datasets:
        writer = ShardWriter(
            config.processed_dir / dataset,
            schema_for(dataset),
            config.parquet_rows_per_file,
        )
        source_files = 0
        no_data_files = 0
        out_of_range_rows = 0
        duplicate_rows = 0
        for item in sorted(manifest.get("tasks", []), key=lambda value: value["task_id"]):
            if item["dataset"] != dataset:
                continue
            if item["status"] == "no_data":
                no_data_files += 1
                continue
            task = tasks_by_id.get(item["task_id"])
            if task is None:
                continue
            path = config.raw_dir / item["file"]
            if not path.exists():
                raise FileNotFoundError(path)
            source_files += 1
            interval_start = datetime.combine(task.start, datetime.min.time(), tzinfo=UTC)
            interval_end = datetime.combine(task.end, datetime.min.time(), tzinfo=UTC)
            seen: set[str] = set()
            for row in parse_document(path, dataset, zones[task.zone.key], item["file"]):
                if not interval_start <= row["timestamp_utc"] < interval_end:
                    out_of_range_rows += 1
                    continue
                if row["record_id"] in seen:
                    duplicate_rows += 1
                    continue
                seen.add(row["record_id"])
                writer.add(row)
        writer.flush()
        results[dataset] = {
            "rows": writer.rows,
            "files": len(writer.files),
            "source_files": source_files,
            "no_data_files": no_data_files,
            "output_bytes": sum(path.stat().st_size for path in writer.files),
            "out_of_range_rows_removed": out_of_range_rows,
            "duplicate_rows_removed": duplicate_rows,
        }
        print(
            f"Normalized {dataset}: {writer.rows:,} rows in {len(writer.files)} files",
            flush=True,
        )
    atomic_json(config.processed_dir / "normalization_summary.json", results)
    return results
