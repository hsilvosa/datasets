from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
from pyarrow import csv

from . import process as pipeline
from .full_runner import valid_zip
from .run_pipeline import selected_archives
from .schema import COLUMNS, EVENT_SCHEMA, FIELD_TYPES

INTEGER_PATTERN = r"^[+-]?[0-9]+$"
FLOAT_PATTERN = r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"


def numeric_array(values: pa.ChunkedArray, target_type: pa.DataType) -> pa.Array:
    stripped = pc.utf8_trim_whitespace(values)
    pattern = INTEGER_PATTERN if pa.types.is_integer(target_type) else FLOAT_PATTERN
    valid = pc.fill_null(pc.match_substring_regex(stripped, pattern), False)
    cleaned = pc.if_else(valid, stripped, pa.scalar(None, type=pa.string()))
    return pc.cast(cleaned, target_type, safe=False)


def read_batches(path: Path, block_size: int) -> Iterator[pa.Table]:
    """Parse malformed numeric cells as null while retaining every valid event row."""
    with zipfile.ZipFile(path) as archive:
        members = sorted(name for name in archive.namelist() if name.lower().endswith(".csv"))
        if not members:
            raise RuntimeError(f"No CSV member in {path.name}")
        for member in members:
            field_count = pipeline.member_field_count(archive, member)
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
                        column_types={name: pa.string() for name in names},
                        strings_can_be_null=True,
                    ),
                )
                for batch in reader:
                    table = pa.Table.from_batches([batch])
                    for index, name in enumerate(names):
                        target_type = FIELD_TYPES[name]
                        if name == "event_date":
                            converted = pc.strptime(
                                table[name], format="%Y%m%d", unit="s", error_is_null=True
                            ).cast(pa.date32())
                        elif name == "date_added":
                            converted = pc.strptime(
                                table[name],
                                format="%Y%m%d%H%M%S",
                                unit="s",
                                error_is_null=True,
                            )
                        elif pa.types.is_integer(target_type) or pa.types.is_floating(target_type):
                            converted = numeric_array(table[name], target_type)
                        else:
                            converted = table[name]
                        table = table.set_column(index, name, converted)
                    if field_count == 57:
                        table = table.append_column(
                            "source_url", pa.nulls(table.num_rows, type=pa.string())
                        )
                    table = table.append_column(
                        "source_archive",
                        pa.array([path.name] * table.num_rows, type=pa.string()),
                    )
                    yield table.cast(EVENT_SCHEMA)


def main() -> int:
    pipeline.read_batches = read_batches
    pipeline.valid_zip = valid_zip
    pipeline.selected_archives = selected_archives
    return pipeline.main()


if __name__ == "__main__":
    raise SystemExit(main())
