from __future__ import annotations

import argparse
import calendar
import json
import tarfile
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


SCHEMA = pa.schema([
    ("station_id", pa.string()), ("date", pa.date32()), ("element", pa.string()),
    ("value", pa.int32()), ("measurement_flag", pa.string()),
    ("quality_flag", pa.string()), ("source_flag", pa.string()),
])


def parse_dly(line: str):
    station_id, year, month, element = line[:11], int(line[11:15]), int(line[15:17]), line[17:21]
    days = calendar.monthrange(year, month)[1]
    for day in range(1, days + 1):
        field = line[21 + (day - 1) * 8:21 + day * 8]
        value = int(field[:5])
        if value == -9999:
            continue
        yield {
            "station_id": station_id, "date": date(year, month, day), "element": element,
            "value": value, "measurement_flag": field[5].strip(),
            "quality_flag": field[6].strip(), "source_flag": field[7].strip(),
        }


def flush(rows: list[dict], writer: pq.ParquetWriter) -> None:
    if rows:
        writer.write_table(pa.Table.from_pylist(rows, schema=SCHEMA))
        rows.clear()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--output", default="data/processed/observations.parquet")
    parser.add_argument("--batch-rows", type=int, default=250_000)
    parser.add_argument("--limit-members", type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cfg = json.loads((root / args.config).read_text(encoding="utf-8"))
    source = root / "data/raw" / cfg["snapshot_date"] / cfg["archive"]["name"]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    members_seen = 0
    with pq.ParquetWriter(output, SCHEMA, compression="zstd") as writer:
        with tarfile.open(source, "r:gz") as archive:
            for member in archive:
                if not member.isfile() or not member.name.endswith(".dly"):
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                for raw in handle:
                    rows.extend(parse_dly(raw.decode("ascii").rstrip("\r\n")))
                    if len(rows) >= args.batch_rows:
                        flush(rows, writer)
                members_seen += 1
                if args.limit_members and members_seen >= args.limit_members:
                    break
        flush(rows, writer)


if __name__ == "__main__":
    main()
