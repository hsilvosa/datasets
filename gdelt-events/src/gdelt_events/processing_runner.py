from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
from pyarrow import csv

from . import process as pipeline
from .schema import COLUMNS, EVENT_SCHEMA, FIELD_TYPES


def read_batches(path: Path, block_size: int) -> Iterator[pa.Table]:
    """Read both GDELT 1.0 layouts and convert compact source timestamps explicitly."""
    with zipfile.ZipFile(path) as archive:
        members = sorted(name for name in archive.namelist() if name.lower().endswith(".csv"))
        if not members:
            raise RuntimeError(f"No CSV member in {path.name}")
        for member in members:
            field_count = pipeline.member_field_count(archive, member)
            if field_count not in (57, 58):
                raise RuntimeError(f"Unexpected {field_count}-column row in {path.name}:{member}")
            names = COLUMNS[:field_count]
            input_types = {name: FIELD_TYPES[name] for name in names}
            input_types["event_date"] = pa.string()
            input_types["date_added"] = pa.string()
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
                        column_types=input_types,
                        strings_can_be_null=True,
                    ),
                )
                for batch in reader:
                    table = pa.Table.from_batches([batch])
                    event_date = pc.strptime(
                        table["event_date"], format="%Y%m%d", unit="s", error_is_null=True
                    ).cast(pa.date32())
                    date_added = pc.strptime(
                        table["date_added"],
                        format="%Y%m%d%H%M%S",
                        unit="s",
                        error_is_null=True,
                    )
                    table = table.set_column(
                        table.schema.get_field_index("event_date"), "event_date", event_date
                    )
                    table = table.set_column(
                        table.schema.get_field_index("date_added"), "date_added", date_added
                    )
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
    return pipeline.main()


if __name__ == "__main__":
    raise SystemExit(main())
