from __future__ import annotations

import csv
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import StringIO
from typing import Any

from .config import Config
from .extract import shard_queries


def repair_mojibake(value: str) -> str:
    repaired = value.strip().replace("\ufffdn", "ón")
    for _ in range(2):
        if not any(marker in repaired for marker in ("Ã", "Â", "\x80", "\x81", "\x8d", "\x93")):
            break
        try:
            candidate = repaired.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if candidate == repaired:
            break
        repaired = candidate
    return repaired


def optional_float(value: str) -> float | None:
    value = value.strip().replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


ROMAN_INTENSITY = {
    "I": 1.0,
    "II": 2.0,
    "III": 3.0,
    "IV": 4.0,
    "V": 5.0,
    "VI": 6.0,
    "VII": 7.0,
    "VIII": 8.0,
    "IX": 9.0,
    "X": 10.0,
    "XI": 11.0,
    "XII": 12.0,
}

FOREIGN_LOCATION_SUFFIXES = {
    "AND": ("AD", "Andorra"),
    "ARG": ("DZ", "Algeria"),
    "FR": ("FR", "France"),
    "FRA": ("FR", "France"),
    "MAC": ("MA", "Morocco"),
    "POR": ("PT", "Portugal"),
}

SPANISH_LOCATION_SUFFIXES = {
    "A",
    "AB",
    "AL",
    "AV",
    "B",
    "BA",
    "BI",
    "BU",
    "C",
    "CA",
    "CC",
    "CE",
    "CO",
    "CR",
    "CS",
    "CU",
    "F",
    "FV",
    "G",
    "GC",
    "GE",
    "GI",
    "GR",
    "GU",
    "H",
    "HE",
    "HU",
    "I",
    "IB",
    "IBZ",
    "IFV",
    "IG",
    "IGC",
    "IGM",
    "IHI",
    "IL",
    "ILP",
    "ILZ",
    "IMA",
    "IME",
    "ITF",
    "J",
    "L",
    "LE",
    "LO",
    "LP",
    "LU",
    "LZ",
    "M",
    "MA",
    "ML",
    "MU",
    "N",
    "NA",
    "O",
    "OR",
    "OU",
    "P",
    "PM",
    "PO",
    "S",
    "SA",
    "SE",
    "SG",
    "SO",
    "SS",
    "T",
    "TE",
    "TF",
    "TO",
    "V",
    "VA",
    "VI",
    "Z",
    "ZA",
}


def intensity_numeric(value: str) -> float | None:
    numeric = optional_float(value)
    if numeric is not None:
        return numeric if numeric >= 0 else None
    parts = [ROMAN_INTENSITY.get(part) for part in value.strip().upper().split("-")]
    if not parts or any(part is None for part in parts):
        return None
    return sum(parts) / len(parts)


def location_country(location: str | None) -> tuple[str | None, str | None]:
    if not location or "." not in location:
        return None, None
    suffix = location.rsplit(".", 1)[1].split(",", 1)[0].strip().upper()
    if suffix in FOREIGN_LOCATION_SUFFIXES:
        return FOREIGN_LOCATION_SUFFIXES[suffix]
    if suffix in SPANISH_LOCATION_SUFFIXES:
        return "ES", "Spain"
    return None, None


def parse_csv(content: bytes, max_rows: int | None = None) -> list[dict[str, Any]]:
    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(StringIO(text), delimiter=";")
    next(reader, None)
    rows: list[dict[str, Any]] = []
    for values in reader:
        if not values or not any(item.strip() for item in values):
            continue
        if len(values) < 10:
            raise ValueError(f"Unexpected IGN CSV row with {len(values)} columns")
        values = [repair_mojibake(item) for item in values[:10]]
        occurred = datetime.strptime(
            f"{values[1]} {values[2]}", "%d/%m/%Y %H:%M:%S"
        ).replace(tzinfo=UTC)
        country_code, country_name = location_country(values[9] or None)
        rows.append(
            {
                "event_id": values[0],
                "occurred_at_utc": occurred.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                ),
                "latitude": optional_float(values[3]),
                "longitude": optional_float(values[4]),
                "depth_km": optional_float(values[5]),
                "maximum_intensity": values[6] or None,
                "maximum_intensity_numeric": intensity_numeric(values[6]),
                "magnitude": optional_float(values[7]),
                "magnitude_type_code": values[8] or None,
                "location": values[9] or None,
                "country_code": country_code,
                "country_name": country_name,
                "source_format": "csv",
            }
        )
        if max_rows is not None and len(rows) >= max_rows:
            break
    return rows


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.current_row = []
        elif tag == "td" and self.current_row is not None:
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.current_cell is not None and self.current_row is not None:
            self.current_row.append(" ".join(self.current_cell).strip())
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            self.rows.append(self.current_row)
            self.current_row = None


def parse_html(content: bytes) -> list[dict[str, Any]]:
    parser = _TableParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    rows = []
    for values in parser.rows:
        if len(values) < 11 or values[1].count("/") != 2:
            continue
        occurred = datetime.strptime(
            f"{values[1]} {values[2]}", "%d/%m/%Y %H:%M:%S"
        ).replace(tzinfo=UTC)
        magnitude_type = values[8] if values[8] not in {"", "null"} else None
        intensity = values[9] if values[9] not in {"", "-1"} else None
        country_code, country_name = location_country(values[10] or None)
        rows.append(
            {
                "event_id": values[0],
                "occurred_at_utc": occurred.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                ),
                "latitude": optional_float(values[4]),
                "longitude": optional_float(values[5]),
                "depth_km": optional_float(values[6]),
                "maximum_intensity": intensity,
                "maximum_intensity_numeric": intensity_numeric(intensity or ""),
                "magnitude": optional_float(values[7]),
                "magnitude_type_code": magnitude_type,
                "location": values[10] or None,
                "country_code": country_code,
                "country_name": country_name,
                "source_format": "html_fallback",
            }
        )
    return rows


def normalize(config: Config) -> dict[str, str | int]:
    raw_paths = [config.raw_dir / filename for filename, _query in shard_queries(config)]
    raw_paths = [path for path in raw_paths if path.exists()]
    if not raw_paths:
        raise FileNotFoundError(f"Run download first: {config.raw_dir}")
    rows: list[dict[str, Any]] = []
    for raw_path in raw_paths:
        remaining = None if config.max_rows is None else config.max_rows - len(rows)
        if remaining == 0:
            break
        if raw_path.stat().st_size:
            rows.extend(parse_csv(raw_path.read_bytes(), remaining))
    for filename in config.html_fallback_files or []:
        path = config.raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing configured HTML fallback: {path}")
        rows.extend(parse_html(path.read_bytes()))
    import pyarrow as pa
    import pyarrow.parquet as pq

    output_dir = config.processed_dir / "earthquakes"
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_file in output_dir.glob("*.parquet"):
        old_file.unlink()
    schema = pa.schema(
        [
            ("event_id", pa.string()),
            ("occurred_at_utc", pa.timestamp("s", tz="UTC")),
            ("latitude", pa.float64()),
            ("longitude", pa.float64()),
            ("depth_km", pa.float64()),
            ("maximum_intensity", pa.string()),
            ("maximum_intensity_numeric", pa.float64()),
            ("magnitude", pa.float64()),
            ("magnitude_type_code", pa.string()),
            ("location", pa.string()),
            ("country_code", pa.string()),
            ("country_name", pa.string()),
            ("source_format", pa.string()),
        ]
    )
    for row in rows:
        row["occurred_at_utc"] = datetime.fromisoformat(row["occurred_at_utc"])
    for index in range(0, len(rows), config.parquet_rows_per_file):
        shard = rows[index : index + config.parquet_rows_per_file]
        path = output_dir / f"train-{index // config.parquet_rows_per_file:05d}.parquet"
        pq.write_table(pa.Table.from_pylist(shard, schema=schema), path, compression="zstd")
    return {
        "processed_dir": str(output_dir),
        "rows": len(rows),
        "files": len(list(output_dir.glob("*.parquet"))),
    }
