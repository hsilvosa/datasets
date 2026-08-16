from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from .config import Config
from .io_utils import atomic_json

SOURCE_COLUMNS = [
    "Captured Time",
    "Latitude",
    "Longitude",
    "Value",
    "Unit",
    "Location Name",
    "Device ID",
    "MD5Sum",
    "Height",
    "Surface",
    "Radiation",
    "Uploaded Time",
    "Loader ID",
]

SOURCE_TYPES = {
    "Captured Time": pa.string(),
    "Latitude": pa.float64(),
    "Longitude": pa.float64(),
    "Value": pa.float64(),
    "Unit": pa.string(),
    "Location Name": pa.string(),
    "Device ID": pa.int64(),
    "MD5Sum": pa.string(),
    "Height": pa.float64(),
    "Surface": pa.string(),
    "Radiation": pa.string(),
    "Uploaded Time": pa.string(),
    "Loader ID": pa.int64(),
}

SCHEMA = pa.schema(
    [
        pa.field("captured_at", pa.timestamp("us")),
        pa.field("latitude", pa.float64()),
        pa.field("longitude", pa.float64()),
        pa.field("value", pa.float64()),
        pa.field("unit", pa.string()),
        pa.field("location_name", pa.string()),
        pa.field("device_id", pa.int64()),
        pa.field("md5sum", pa.string()),
        pa.field("height", pa.float64()),
        pa.field("surface", pa.string()),
        pa.field("radiation", pa.string()),
        pa.field("uploaded_at", pa.timestamp("us")),
        pa.field("loader_id", pa.int64()),
    ]
)


def transform(table: pa.Table) -> pa.Table:
    columns = {
        "captured_at": pc.cast(table["Captured Time"], pa.timestamp("us"), safe=False),
        "latitude": table["Latitude"],
        "longitude": table["Longitude"],
        "value": table["Value"],
        "unit": table["Unit"],
        "location_name": table["Location Name"],
        "device_id": table["Device ID"],
        "md5sum": table["MD5Sum"],
        "height": table["Height"],
        "surface": table["Surface"],
        "radiation": table["Radiation"],
        "uploaded_at": pc.cast(table["Uploaded Time"], pa.timestamp("us"), safe=False),
        "loader_id": table["Loader ID"],
    }
    return pa.Table.from_arrays([columns[field.name] for field in SCHEMA], schema=SCHEMA)


def write_shard(table: pa.Table, directory: Path, index: int) -> Path:
    path = directory / f"part-{index:05d}.parquet"
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=6,
        row_group_size=250_000,
        write_statistics=True,
    )
    return path


def normalize(config: Config) -> dict[str, int]:
    if not config.archive_path.exists():
        raise FileNotFoundError(config.archive_path)
    target = config.processed_dir / "measurements"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    pending: list[pa.Table] = []
    pending_rows = 0
    total_rows = 0
    file_index = 0
    with tarfile.open(config.archive_path, "r:gz") as archive:
        member = archive.next()
        if member is None or not member.isfile() or not member.name.endswith(".csv"):
            raise RuntimeError("The first archive member is not the expected CSV")
        handle = archive.extractfile(member)
        if handle is None:
            raise RuntimeError("Could not open CSV member")
        reader = pacsv.open_csv(
            pa.PythonFile(handle),
            read_options=pacsv.ReadOptions(block_size=config.csv_block_size, use_threads=True),
            parse_options=pacsv.ParseOptions(newlines_in_values=False),
            convert_options=pacsv.ConvertOptions(
                column_types=SOURCE_TYPES,
                null_values=[""],
                strings_can_be_null=True,
            ),
        )
        for batch_index, batch in enumerate(reader, 1):
            table = transform(pa.Table.from_batches([batch]))
            pending.append(table)
            pending_rows += table.num_rows
            while pending_rows >= config.rows_per_file:
                combined = pa.concat_tables(pending)
                write_shard(combined.slice(0, config.rows_per_file), target, file_index)
                remainder = combined.slice(config.rows_per_file)
                total_rows += config.rows_per_file
                file_index += 1
                pending = [remainder] if remainder.num_rows else []
                pending_rows = remainder.num_rows
            if batch_index % 25 == 0:
                print(f"Safecast normalize: {total_rows + pending_rows:,} rows", flush=True)
    if pending_rows:
        write_shard(pa.concat_tables(pending), target, file_index)
        total_rows += pending_rows
        file_index += 1
    summary = {"rows": total_rows, "parquet_files": file_index}
    atomic_json(config.processed_dir / "normalization_summary.json", summary)
    return summary
