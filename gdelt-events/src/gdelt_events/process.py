from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from pyarrow import csv

from .io_utils import atomic_json, file_hash
from .schema import COLUMNS, EVENT_SCHEMA, FIELD_TYPES


@dataclass(frozen=True)
class ProcessingConfig:
    raw_dir: Path
    processed_dir: Path
    artifacts_dir: Path
    staging_dir: Path
    csv_block_size: int
    parquet_rows_per_file: int
    unavailable_files: list[str]
    md5_overrides: dict[str, str]

    @classmethod
    def load(cls, path: str | Path) -> ProcessingConfig:
        config_path = Path(path).resolve()
        payload: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
        root = config_path.parent.parent
        for key in ("raw_dir", "processed_dir", "artifacts_dir", "staging_dir"):
            value = Path(payload[key])
            payload[key] = value if value.is_absolute() else (root / value).resolve()
        config = cls(**payload)
        config.validate(root)
        return config

    def validate(self, root: Path) -> None:
        for path in (self.raw_dir, self.processed_dir, self.artifacts_dir, self.staging_dir):
            if root not in path.parents and path != root:
                raise ValueError(f"Configured path is outside the project: {path}")
        if self.csv_block_size < 1 or self.parquet_rows_per_file < 1:
            raise ValueError("Processing sizes must be positive")
        if any(not name.endswith(".zip") for name in self.unavailable_files):
            raise ValueError("unavailable_files must contain ZIP filenames")
        if any(
            len(value) != 32 or any(character not in "0123456789abcdef" for character in value)
            for value in self.md5_overrides.values()
        ):
            raise ValueError("md5_overrides values must be lowercase MD5 hashes")


def source_manifest(config: ProcessingConfig) -> dict[str, Any]:
    path = config.raw_dir / "snapshot_manifest.json"
    if not path.exists():
        raise RuntimeError("snapshot_manifest.json is missing; run the downloader first")
    return json.loads(path.read_text(encoding="utf-8"))


def selected_archives(config: ProcessingConfig) -> list[dict[str, Any]]:
    excluded = set(config.unavailable_files)
    archives = [
        dict(item) for item in source_manifest(config)["archives"] if item["name"] not in excluded
    ]
    for item in archives:
        if item["name"] in config.md5_overrides:
            item["published_md5"] = item["md5"]
            item["md5"] = config.md5_overrides[item["name"]]
            item["md5_source"] = "current server object ETag"
        else:
            item["md5_source"] = "GDELT md5sums manifest"
    return archives


def valid_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            return bool(members) and archive.testzip() is None
    except (OSError, zipfile.BadZipFile):
        return False


def verify(config: ProcessingConfig) -> dict[str, Any]:
    archives = selected_archives(config)
    invalid: list[dict[str, str]] = []
    total_bytes = 0
    for index, item in enumerate(archives, 1):
        path = config.raw_dir / item["name"]
        if not path.exists():
            invalid.append({"name": item["name"], "reason": "missing"})
            continue
        total_bytes += path.stat().st_size
        if path.stat().st_size != item["bytes"]:
            invalid.append({"name": item["name"], "reason": "size mismatch"})
        elif file_hash(path, "md5") != item["md5"]:
            invalid.append({"name": item["name"], "reason": "MD5 mismatch"})
        elif not valid_zip(path):
            invalid.append({"name": item["name"], "reason": "invalid ZIP"})
        if index == 1 or index % 250 == 0 or index == len(archives):
            print(f"GDELT verify {index}/{len(archives)}", flush=True)
    result = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "snapshot_date": source_manifest(config)["snapshot_date"],
        "manifest_archives": len(source_manifest(config)["archives"]),
        "available_archives": len(archives),
        "valid_archives": len(archives) - len(invalid),
        "compressed_bytes": total_bytes,
        "source_unavailable": config.unavailable_files,
        "source_checksum_overrides": config.md5_overrides,
        "invalid": invalid,
    }
    atomic_json(config.artifacts_dir / "source_quality.json", result)
    return result


def member_field_count(archive: zipfile.ZipFile, member: str) -> int:
    with archive.open(member) as handle:
        return len(handle.readline().rstrip(b"\r\n").split(b"\t"))


def read_batches(path: Path, block_size: int) -> Iterator[pa.Table]:
    with zipfile.ZipFile(path) as archive:
        members = sorted(name for name in archive.namelist() if name.lower().endswith(".csv"))
        if not members:
            raise RuntimeError(f"No CSV member in {path.name}")
        for member in members:
            field_count = member_field_count(archive, member)
            if field_count not in (57, 58):
                raise RuntimeError(f"Unexpected {field_count}-column row in {path.name}:{member}")
            names = COLUMNS[:field_count]
            with archive.open(member) as handle:
                reader = csv.open_csv(
                    handle,
                    read_options=csv.ReadOptions(
                        column_names=names,
                        block_size=block_size,
                        encoding="utf8",
                    ),
                    parse_options=csv.ParseOptions(delimiter="\t", quote_char=False),
                    convert_options=csv.ConvertOptions(
                        column_types={name: FIELD_TYPES[name] for name in names},
                        timestamp_parsers=["%Y%m%d", "%Y%m%d%H%M%S"],
                        strings_can_be_null=True,
                    ),
                )
                for batch in reader:
                    table = pa.Table.from_batches([batch])
                    if field_count == 57:
                        table = table.append_column(
                            "source_url", pa.nulls(table.num_rows, type=pa.string())
                        )
                    table = table.append_column(
                        "source_archive",
                        pa.array([path.name] * table.num_rows, type=pa.string()),
                    )
                    yield table.cast(EVENT_SCHEMA)


def normalize(config: ProcessingConfig) -> dict[str, Any]:
    source_check = verify(config)
    if source_check["invalid"]:
        raise RuntimeError(f"Source verification failed for {len(source_check['invalid'])} archives")
    archives = selected_archives(config)
    target = config.processed_dir / "events"
    if target.parent != config.processed_dir:
        raise RuntimeError(f"Unsafe processed target: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    writer: pq.ParquetWriter | None = None
    shard_rows = 0
    total_rows = 0
    shard_index = 0

    def close_writer() -> None:
        nonlocal writer
        if writer is not None:
            writer.close()
            writer = None

    try:
        for archive_index, item in enumerate(archives, 1):
            path = config.raw_dir / item["name"]
            if archive_index == 1 or archive_index % 25 == 0 or archive_index == len(archives):
                print(f"GDELT normalize {archive_index}/{len(archives)}: {path.name}", flush=True)
            for table in read_batches(path, config.csv_block_size):
                if writer is None or (
                    shard_rows and shard_rows + table.num_rows > config.parquet_rows_per_file
                ):
                    close_writer()
                    output = target / f"part-{shard_index:05d}.parquet"
                    writer = pq.ParquetWriter(
                        output,
                        EVENT_SCHEMA,
                        compression="zstd",
                        use_dictionary=True,
                        write_statistics=True,
                    )
                    shard_index += 1
                    shard_rows = 0
                writer.write_table(table)
                shard_rows += table.num_rows
                total_rows += table.num_rows
    finally:
        close_writer()
    result = {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "source_archives": len(archives),
        "rows": total_rows,
        "parquet_files": shard_index,
        "compressed_bytes": sum(path.stat().st_size for path in target.glob("*.parquet")),
    }
    atomic_json(config.processed_dir / "normalization_summary.json", result)
    return result


def analyze(config: ProcessingConfig) -> dict[str, Any]:
    paths = sorted((config.processed_dir / "events").glob("*.parquet"))
    if not paths:
        raise RuntimeError("No normalized Parquet files were found")
    dataset = ds.dataset(paths, format="parquet")
    rows = sum(pq.ParquetFile(path).metadata.num_rows for path in paths)
    minimum_date = None
    maximum_date = None
    null_ids = 0
    invalid_coordinates = 0
    null_counts: Counter[str] = Counter()
    year_counts: Counter[int] = Counter()
    quad_class_counts: Counter[int] = Counter()
    root_code_counts: Counter[str] = Counter()
    country_counts: Counter[str] = Counter()
    numeric_totals = {
        "goldstein_scale": {"count": 0, "sum": 0.0, "min": None, "max": None},
        "num_mentions": {"count": 0, "sum": 0.0, "min": None, "max": None},
        "avg_tone": {"count": 0, "sum": 0.0, "min": None, "max": None},
    }

    def update_counts(counter: Counter[Any], values: pa.Array) -> None:
        counts = pc.value_counts(values)
        for item in counts.to_pylist():
            if item["values"] is not None:
                counter[item["values"]] += item["counts"]

    def update_numeric(name: str, values: pa.Array) -> None:
        valid_count = len(values) - values.null_count
        if not valid_count:
            return
        summary = numeric_totals[name]
        bounds = pc.min_max(values).as_py()
        summary["count"] += valid_count
        summary["sum"] += float(pc.sum(values).as_py())
        summary["min"] = (
            bounds["min"] if summary["min"] is None else min(summary["min"], bounds["min"])
        )
        summary["max"] = (
            bounds["max"] if summary["max"] is None else max(summary["max"], bounds["max"])
        )
    scanner = dataset.scanner(
        columns=[
            "global_event_id",
            "event_date",
            "actor1_code",
            "actor2_code",
            "event_root_code",
            "quad_class",
            "goldstein_scale",
            "num_mentions",
            "avg_tone",
            "action_geo_country_code",
            "action_geo_latitude",
            "action_geo_longitude",
            "source_url",
        ],
        batch_size=1_000_000,
    )
    for batch in scanner.to_batches():
        null_ids += batch.column("global_event_id").null_count
        dates = pc.min_max(batch.column("event_date")).as_py()
        if dates["min"] is not None:
            minimum_date = dates["min"] if minimum_date is None else min(minimum_date, dates["min"])
            maximum_date = dates["max"] if maximum_date is None else max(maximum_date, dates["max"])
        latitude = batch.column("action_geo_latitude")
        longitude = batch.column("action_geo_longitude")
        bad = pc.or_(pc.less(latitude, -90), pc.greater(latitude, 90))
        bad = pc.or_(bad, pc.or_(pc.less(longitude, -180), pc.greater(longitude, 180)))
        invalid_coordinates += pc.sum(pc.fill_null(bad, False)).as_py()
        for name in (
            "event_date",
            "actor1_code",
            "actor2_code",
            "action_geo_country_code",
            "action_geo_latitude",
            "action_geo_longitude",
            "source_url",
        ):
            null_counts[name] += batch.column(name).null_count
        update_counts(year_counts, pc.year(batch.column("event_date")))
        update_counts(quad_class_counts, batch.column("quad_class"))
        update_counts(root_code_counts, batch.column("event_root_code"))
        update_counts(country_counts, batch.column("action_geo_country_code"))
        for name in numeric_totals:
            update_numeric(name, batch.column(name))
    profile = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "rows": rows,
        "parquet_files": len(paths),
        "compressed_bytes": sum(path.stat().st_size for path in paths),
        "columns": len(dataset.schema),
        "event_date_min": minimum_date.isoformat() if minimum_date else None,
        "event_date_max": maximum_date.isoformat() if maximum_date else None,
    }
    schema = {
        "fields": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in dataset.schema
        ]
    }
    quality = {
        "rows": rows,
        "files": len(paths),
        "null_global_event_id": null_ids,
        "invalid_action_coordinates": invalid_coordinates,
        "schema_consistent": all(pq.read_schema(path).equals(dataset.schema) for path in paths),
        "source_unavailable": config.unavailable_files,
    }
    checksums = {
        str(path.relative_to(config.processed_dir)).replace("\\", "/"): file_hash(path, "sha256")
        for path in paths
    }
    provenance = {
        "publisher": "The GDELT Project",
        "product": "GDELT 1.0 Event Database",
        "snapshot_date": source_manifest(config)["snapshot_date"],
        "source_archives": len(selected_archives(config)),
        "source_manifest_sha256": file_hash(config.raw_dir / "snapshot_manifest.json", "sha256"),
        "processing_config_sha256": hashlib.sha256(
            json.dumps(
                {
                    "csv_block_size": config.csv_block_size,
                    "parquet_rows_per_file": config.parquet_rows_per_file,
                    "unavailable_files": config.unavailable_files,
                    "md5_overrides": config.md5_overrides,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }
    quad_labels = {
        1: "verbal cooperation",
        2: "material cooperation",
        3: "verbal conflict",
        4: "material conflict",
    }
    analysis = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "rows": rows,
        "events_by_year": {str(key): value for key, value in sorted(year_counts.items())},
        "quad_class": {
            str(key): {
                "label": quad_labels.get(key, "unknown"),
                "rows": value,
                "percent": round(value * 100 / rows, 4),
            }
            for key, value in sorted(quad_class_counts.items())
        },
        "top_event_root_codes": [
            {"code": key, "rows": value, "percent": round(value * 100 / rows, 4)}
            for key, value in root_code_counts.most_common(20)
        ],
        "top_action_geo_country_codes": [
            {"code": key, "rows": value, "percent": round(value * 100 / rows, 4)}
            for key, value in country_counts.most_common(20)
        ],
        "field_coverage": {
            name: {
                "non_null": rows - value,
                "percent": round((rows - value) * 100 / rows, 4),
            }
            for name, value in sorted(null_counts.items())
        },
        "numeric_summary": {
            name: {
                "count": summary["count"],
                "mean": round(summary["sum"] / summary["count"], 6),
                "min": summary["min"],
                "max": summary["max"],
            }
            for name, summary in numeric_totals.items()
        },
    }
    atomic_json(config.artifacts_dir / "profile.json", profile)
    atomic_json(config.artifacts_dir / "schema.json", schema)
    atomic_json(config.artifacts_dir / "quality.json", quality)
    atomic_json(config.artifacts_dir / "checksums.json", checksums)
    atomic_json(config.artifacts_dir / "provenance.json", provenance)
    atomic_json(config.artifacts_dir / "analysis.json", analysis)
    return profile


CARD_HEADER = """---
license: other
license_name: gdelt-terms-of-use
license_link: https://www.gdeltproject.org/about.html#termsofuse
pretty_name: GDELT 1.0 Events Historical Snapshot
size_categories:
- 100M<n<1B
tags:
- events
- geopolitics
- news
- time-series
- geospatial
- cameo
- multilingual
configs:
- config_name: events
  data_files:
  - split: train
    path: data/events/*.parquet
---
"""


def stage(config: ProcessingConfig) -> Path:
    if config.staging_dir.exists():
        shutil.rmtree(config.staging_dir)
    data_target = config.staging_dir / "data" / "events"
    artifacts_target = config.staging_dir / "artifacts"
    data_target.mkdir(parents=True)
    artifacts_target.mkdir(parents=True)
    sources = sorted((config.processed_dir / "events").glob("*.parquet"))
    if not sources:
        raise RuntimeError("No normalized Parquet files were found")
    for source in sources:
        shutil.copy2(source, data_target / source.name)
    for source in sorted(config.artifacts_dir.glob("*.json")):
        shutil.copy2(source, artifacts_target / source.name)
    card = Path(__file__).resolve().parents[2] / "DATASET_CARD.md"
    (config.staging_dir / "README.md").write_text(
        CARD_HEADER + "\n" + card.read_text(encoding="utf-8"), encoding="utf-8"
    )
    manifest = {
        "included": ["README.md", "data/events/*.parquet", "artifacts/*.json"],
        "excluded": ["source ZIP archives", "partial downloads", "local logs"],
    }
    (config.staging_dir / "UPLOAD_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return config.staging_dir


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Process the historical GDELT Event Database")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("verify", "normalize", "analyze", "stage", "run"):
        command = commands.add_parser(name)
        command.add_argument("--config", default="configs/processing.json")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = ProcessingConfig.load(args.config)
    if args.command == "verify":
        output = verify(config)
    elif args.command == "normalize":
        output = normalize(config)
    elif args.command == "analyze":
        output = analyze(config)
    elif args.command == "stage":
        output = {"staging_dir": str(stage(config))}
    else:
        output = {"source_quality": verify(config)}
        output["normalization"] = normalize(config)
        output["profile"] = analyze(config)
        output["staging_dir"] = str(stage(config))
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
