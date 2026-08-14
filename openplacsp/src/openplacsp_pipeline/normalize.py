from __future__ import annotations

import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .config import Config
from .io_utils import atomic_json
from .parser import iter_entries
from .tasks import build_tasks

SCHEMAS = {
    "versions": pa.schema(
        [
            ("version_id", pa.string(), False),
            ("atom_id", pa.string()),
            ("updated_at", pa.timestamp("us", tz="UTC")),
            ("published_at", pa.timestamp("us", tz="UTC")),
            ("title", pa.string()),
            ("summary", pa.string()),
            ("entry_url", pa.string()),
            ("is_deleted", pa.bool_(), False),
            ("folder_id", pa.string()),
            ("status_code", pa.string()),
            ("project_name", pa.string()),
            ("contract_type_code", pa.string()),
            ("contract_subtype_code", pa.string()),
            ("estimated_value", pa.float64()),
            ("budget_tax_exclusive", pa.float64()),
            ("budget_total", pa.float64()),
            ("currency", pa.string()),
            ("procedure_code", pa.string()),
            ("contracting_party_name", pa.string()),
            ("contracting_party_nif", pa.string()),
            ("contracting_party_platform_id", pa.string()),
            ("contracting_party_type_code", pa.string()),
            ("buyer_profile_url", pa.string()),
            ("source_archive", pa.string(), False),
            ("source_member", pa.string(), False),
        ]
    ),
    "lots": pa.schema(
        [
            ("version_id", pa.string(), False),
            ("lot_id", pa.string(), False),
            ("name", pa.string()),
            ("budget_tax_exclusive", pa.float64()),
            ("budget_total", pa.float64()),
            ("currency", pa.string()),
        ]
    ),
    "cpv_codes": pa.schema(
        [
            ("version_id", pa.string(), False),
            ("lot_id", pa.string()),
            ("cpv_code", pa.string(), False),
            ("cpv_name", pa.string()),
        ]
    ),
    "awards": pa.schema(
        [
            ("version_id", pa.string(), False),
            ("result_position", pa.int32(), False),
            ("winner_position", pa.int32(), False),
            ("result_code", pa.string()),
            ("description", pa.string()),
            ("award_date", pa.date32()),
            ("received_tenders", pa.int64()),
            ("lot_id", pa.string()),
            ("winner_name", pa.string()),
            ("winner_nif", pa.string()),
            ("award_tax_exclusive", pa.float64()),
            ("currency", pa.string()),
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
    return date.fromisoformat(value[:10])


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
        if not rows:
            return
        buffer = self.buffers[name]
        buffer.extend(rows)
        while len(buffer) >= self.rows_per_file:
            self._write(name, buffer[: self.rows_per_file])
            del buffer[: self.rows_per_file]

    def _write(self, name: str, rows: list[dict]) -> None:
        if name == "versions":
            for row in rows:
                row["updated_at"] = parse_datetime(row["updated_at"])
                row["published_at"] = parse_datetime(row["published_at"])
        elif name == "awards":
            for row in rows:
                row["award_date"] = parse_date(row["award_date"])
        index = self.files[name]
        table = pa.Table.from_pylist(rows, schema=SCHEMAS[name])
        pq.write_table(
            table,
            self.root / name / f"part-{index:05d}.parquet",
            compression="zstd",
            write_statistics=True,
        )
        self.files[name] += 1
        self.counts[name] += len(rows)

    def close(self) -> None:
        for name, rows in self.buffers.items():
            if rows:
                self._write(name, rows)
                rows.clear()


def normalize(config: Config) -> dict[str, object]:
    planned = [task.path for task in build_tasks(config) if task.path.exists()]
    archives = planned or sorted(config.raw_dir.glob("*.zip"))
    if not archives:
        raise FileNotFoundError(f"No OpenPLACSP ZIP archives found in {config.raw_dir}")
    writer = ShardedWriter(config.processed_dir, config.parquet_rows_per_file)
    members = 0
    entries = 0
    for archive_path in archives:
        print(f"OpenPLACSP normalize {archive_path.name}", flush=True)
        with zipfile.ZipFile(archive_path) as archive:
            for member in sorted(archive.namelist()):
                if not member.lower().endswith((".atom", ".xml")):
                    continue
                members += 1
                with archive.open(member) as handle:
                    for parsed in iter_entries(
                        handle, source_archive=archive_path.name, source_member=member
                    ):
                        entries += 1
                        writer.add("versions", [parsed.version])
                        writer.add("lots", parsed.lots)
                        writer.add("cpv_codes", parsed.cpv_codes)
                        writer.add("awards", parsed.awards)
    writer.close()
    summary = {
        "archives": len(archives),
        "atom_members": members,
        "entries": entries,
        "tables": writer.counts,
        "parquet_files": writer.files,
    }
    atomic_json(config.processed_dir / "normalization_summary.json", summary)
    return summary
