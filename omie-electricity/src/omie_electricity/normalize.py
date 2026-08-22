from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .config import Config

logger = logging.getLogger(__name__)

OMIE_MARGINAL_SCHEMA = pa.schema([
    ("date", pa.date32()),
    ("year", pa.int16()),
    ("month", pa.int8()),
    ("day", pa.int8()),
    ("hour", pa.int8()),
    ("price_es", pa.float64()),
    ("price_pt", pa.float64()),
])

OMIE_CURVES_SCHEMA = pa.schema([
    ("date", pa.date32()),
    ("year", pa.int16()),
    ("hour", pa.int8()),
    ("country", pa.string()),
    ("offer_type", pa.string()),  # 'C' (Compra / Buy) or 'V' (Venta / Sell)
    ("energy_mwh", pa.float64()),
    ("price_eur_mwh", pa.float64()),
    ("status", pa.string()),  # 'O' (Ofertada) or 'C' (Casada)
])


def parse_float_es(val_str: str) -> float:
    clean = val_str.strip().replace(".", "").replace(",", ".")
    return float(clean)


def parse_omie_marginal_line(line: str) -> dict[str, Any] | None:
    parts = [p.strip() for p in line.split(";") if p.strip()]
    if not parts or len(parts) < 5 or not parts[0].isdigit():
        return None
    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        hour = int(parts[3])
        price_es = parse_float_es(parts[4])
        price_pt = parse_float_es(parts[5]) if len(parts) >= 6 else price_es
        return {
            "date": date(year, month, day),
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "price_es": price_es,
            "price_pt": price_pt,
        }
    except (ValueError, IndexError):
        return None


def parse_curva_pbc_file(file_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    content = file_path.read_text(encoding="latin-1", errors="replace")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("OMIE") or line.startswith("Hora;"):
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 8 or not parts[0].isdigit():
            continue
        try:
            hour = int(parts[0])
            d_parts = parts[1].split("/")
            if len(d_parts) != 3:
                continue
            row_date = date(int(d_parts[2]), int(d_parts[1]), int(d_parts[0]))
            country = parts[2]
            offer_type = parts[4]
            energy = parse_float_es(parts[5])
            price = parse_float_es(parts[6])
            status = parts[7]

            rows.append({
                "date": row_date,
                "year": row_date.year,
                "hour": hour,
                "country": country,
                "offer_type": offer_type,
                "energy_mwh": energy,
                "price_eur_mwh": price,
                "status": status,
            })
        except (ValueError, IndexError):
            continue
    return rows


def normalize(config: Config) -> dict[str, Any]:
    """Normalize raw OMIE files (marginal prices + streaming bidding curves) to Parquet."""
    config.processed_dir.mkdir(parents=True, exist_ok=True)

    # 1. Normalize marginal prices
    raw_marginal = sorted(config.raw_dir.glob("*/marginalpdbc_*.1")) + sorted(config.raw_dir.glob("marginalpdbc_*.1"))
    by_year_marginal: dict[int, list[dict[str, Any]]] = {}
    for f in raw_marginal:
        content = f.read_text(encoding="latin-1", errors="replace")
        for line in content.splitlines():
            parsed = parse_omie_marginal_line(line.strip())
            if parsed:
                by_year_marginal.setdefault(parsed["year"], []).append(parsed)

    marginal_rows = 0
    for yr, rows in sorted(by_year_marginal.items()):
        rows.sort(key=lambda x: (x["date"], x["hour"]))
        table = pa.Table.from_pylist(rows, schema=OMIE_MARGINAL_SCHEMA)
        out_file = config.processed_dir / f"omie_marginal_prices_{yr}.parquet"
        pq.write_table(table, out_file, compression="zstd")
        marginal_rows += len(rows)

    # 2. Normalize bidding curves with streaming ParquetWriter per year
    raw_curves_by_year: dict[int, list[Path]] = {}
    for f in sorted(config.raw_dir.glob("*/curva_pbc_*.1")) + sorted(config.raw_dir.glob("curva_pbc_*.1")):
        # Extract year from parent or filename
        yr = int(f.parent.name) if f.parent.name.isdigit() else int(f.stem.split("_")[2][:4])
        raw_curves_by_year.setdefault(yr, []).append(f)

    total_curve_rows = 0
    for yr, curve_files in sorted(raw_curves_by_year.items()):
        out_file = config.processed_dir / f"omie_bidding_curves_{yr}.parquet"
        logger.info("Normalizing %d curve files for year %d into %s...", len(curve_files), yr, out_file.name)
        yr_rows = 0
        with pq.ParquetWriter(out_file, OMIE_CURVES_SCHEMA, compression="zstd") as writer:
            for cf in curve_files:
                file_rows = parse_curva_pbc_file(cf)
                if file_rows:
                    batch_table = pa.Table.from_pylist(file_rows, schema=OMIE_CURVES_SCHEMA)
                    writer.write_table(batch_table)
                    yr_rows += len(file_rows)
        total_curve_rows += yr_rows
        logger.info("Wrote %d bidding curve rows to %s", yr_rows, out_file.name)

    return {
        "marginal_prices_total_rows": marginal_rows,
        "bidding_curves_total_rows": total_curve_rows,
        "total_rows": marginal_rows + total_curve_rows,
    }
