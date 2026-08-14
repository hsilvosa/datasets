from __future__ import annotations

import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS

from .catalog import discover
from .config import Config
from .gml import SourceContext, iter_features
from .io_utils import atomic_json

BASE_FIELDS = [
    pa.field("feature_id", pa.string(), nullable=False),
    pa.field("local_id", pa.string()),
    pa.field("namespace", pa.string()),
    pa.field("province_code", pa.string(), nullable=False),
    pa.field("municipality_code", pa.string(), nullable=False),
    pa.field("municipality_name", pa.string(), nullable=False),
    pa.field("begin_lifespan_version", pa.timestamp("us", tz="UTC")),
    pa.field("end_lifespan_version", pa.timestamp("us", tz="UTC")),
    pa.field("source_crs", pa.string(), nullable=False),
    pa.field("geometry", pa.binary()),
    pa.field("bbox_min_x", pa.float64()),
    pa.field("bbox_min_y", pa.float64()),
    pa.field("bbox_max_x", pa.float64()),
    pa.field("bbox_max_y", pa.float64()),
    pa.field("properties_json", pa.string(), nullable=False),
    pa.field("source_archive", pa.string(), nullable=False),
    pa.field("source_member", pa.string(), nullable=False),
]


def geo_schema(extra_fields: list[pa.Field]) -> pa.Schema:
    metadata = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": ["Point", "Polygon", "MultiPolygon"],
                "crs": CRS.from_epsg(4326).to_json_dict(),
                "edges": "planar",
                "bbox": [-19.0, 27.0, 5.0, 44.5],
                "covering": {
                    "bbox": {
                        "xmin": ["bbox_min_x"],
                        "ymin": ["bbox_min_y"],
                        "xmax": ["bbox_max_x"],
                        "ymax": ["bbox_max_y"],
                    }
                },
            }
        },
    }
    return pa.schema(BASE_FIELDS + extra_fields).with_metadata(
        {b"geo": json.dumps(metadata, separators=(",", ":")).encode("utf-8")}
    )


BUILDING_FIELDS = [
    pa.field("condition_of_construction", pa.string()),
    pa.field("construction_begin", pa.date32()),
    pa.field("construction_end", pa.date32()),
    pa.field("current_use", pa.string()),
    pa.field("number_of_building_units", pa.int64()),
    pa.field("number_of_dwellings", pa.int64()),
    pa.field("floors_above_ground", pa.int64()),
    pa.field("floors_below_ground", pa.int64()),
    pa.field("official_area", pa.float64()),
    pa.field("cadastral_parcel_refs", pa.list_(pa.string())),
    pa.field("address_refs", pa.list_(pa.string())),
]

SCHEMAS = {
    "cadastral_parcels": geo_schema(
        [
            pa.field("area_value", pa.float64()),
            pa.field("label", pa.string()),
            pa.field("national_reference", pa.string()),
        ]
    ),
    "cadastral_zonings": geo_schema(
        [
            pa.field("estimated_accuracy", pa.float64()),
            pa.field("label", pa.string()),
            pa.field("level", pa.string()),
            pa.field("level_name", pa.string()),
            pa.field("national_reference", pa.string()),
            pa.field("original_scale_denominator", pa.int64()),
        ]
    ),
    "addresses": geo_schema(
        [
            pa.field("locator_designator", pa.string()),
            pa.field("valid_from", pa.date32()),
            pa.field("valid_to", pa.date32()),
        ]
    ),
    "buildings": geo_schema(BUILDING_FIELDS),
    "building_parts": geo_schema(BUILDING_FIELDS),
    "other_constructions": geo_schema(BUILDING_FIELDS),
    "municipalities": pa.schema(
        [
            pa.field("municipality_code", pa.string(), nullable=False),
            pa.field("municipality_name", pa.string(), nullable=False),
            pa.field("province_code", pa.string(), nullable=False),
            pa.field("parcels_archive_url", pa.string()),
            pa.field("addresses_archive_url", pa.string()),
            pa.field("buildings_archive_url", pa.string()),
        ]
    ),
}


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def typed_row(name: str, row: dict) -> dict:
    row["begin_lifespan_version"] = parse_datetime(row.get("begin_lifespan_version"))
    row["end_lifespan_version"] = parse_datetime(row.get("end_lifespan_version"))
    if name == "addresses":
        row["valid_from"] = parse_date(row.get("valid_from"))
        row["valid_to"] = parse_date(row.get("valid_to"))
    elif name in {"buildings", "building_parts", "other_constructions"}:
        row["construction_begin"] = parse_date(row.get("construction_begin"))
        row["construction_end"] = parse_date(row.get("construction_end"))
    return row


class ShardedWriter:
    def __init__(self, root: Path, rows_per_file: int) -> None:
        self.root = root
        self.rows_per_file = rows_per_file
        self.buffers = {name: [] for name in SCHEMAS}
        self.counts = {name: 0 for name in SCHEMAS}
        self.files = {name: 0 for name in SCHEMAS}
        for name in SCHEMAS:
            target = root / name
            target.mkdir(parents=True, exist_ok=True)
            for stale in target.glob("part-*.parquet"):
                stale.unlink()

    def add(self, name: str, rows: list[dict]) -> None:
        buffer = self.buffers[name]
        buffer.extend(typed_row(name, row) for row in rows)
        while len(buffer) >= self.rows_per_file:
            self.write(name, buffer[: self.rows_per_file])
            del buffer[: self.rows_per_file]

    def write(self, name: str, rows: list[dict]) -> None:
        table = pa.Table.from_pylist(rows, schema=SCHEMAS[name])
        path = self.root / name / f"part-{self.files[name]:05d}.parquet"
        pq.write_table(table, path, compression="zstd", write_statistics=True)
        self.counts[name] += len(rows)
        self.files[name] += 1

    def close(self) -> None:
        for name, rows in self.buffers.items():
            if rows:
                self.write(name, rows)
                rows.clear()


def municipality_rows(tasks) -> list[dict]:
    rows: dict[str, dict] = {}
    for task in tasks:
        row = rows.setdefault(
            task.municipality_code,
            {
                "municipality_code": task.municipality_code,
                "municipality_name": task.municipality_name,
                "province_code": task.province_code,
                "parcels_archive_url": None,
                "addresses_archive_url": None,
                "buildings_archive_url": None,
            },
        )
        row[f"{task.collection}_archive_url"] = task.url
    return [rows[key] for key in sorted(rows)]


def normalize(config: Config) -> dict[str, object]:
    tasks = discover(config)
    missing = [task.path for task in tasks if not task.path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} source archives; run download first")
    writer = ShardedWriter(config.processed_dir, config.parquet_rows_per_file)
    writer.add("municipalities", municipality_rows(tasks))
    members = 0
    for index, task in enumerate(tasks, 1):
        if index % 100 == 0 or index == len(tasks):
            print(f"Cadastre normalize {index}/{len(tasks)}", flush=True)
        with zipfile.ZipFile(task.path) as archive:
            for member in sorted(archive.namelist()):
                if not member.lower().endswith(".gml"):
                    continue
                members += 1
                context = SourceContext(
                    task.province_code,
                    task.municipality_code,
                    task.municipality_name,
                    task.path.name,
                    member,
                )
                with archive.open(member) as handle:
                    for table_name, row in iter_features(handle, context):
                        writer.add(table_name, [row])
    writer.close()
    summary = {
        "archives": len(tasks),
        "gml_members": members,
        "tables": writer.counts,
        "parquet_files": writer.files,
    }
    atomic_json(config.processed_dir / "normalization_summary.json", summary)
    return summary
