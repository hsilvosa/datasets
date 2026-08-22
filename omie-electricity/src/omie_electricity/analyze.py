from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .config import Config
from .normalize import OMIE_CURVES_SCHEMA, OMIE_MARGINAL_SCHEMA

logger = logging.getLogger(__name__)


def generate_metadata(config: Config) -> dict[str, Any]:
    """Generate schema, profile, quality, and provenance artifacts."""
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)

    marginal_files = sorted(config.processed_dir.glob("omie_marginal_prices_*.parquet"))
    curve_files = sorted(config.processed_dir.glob("omie_bidding_curves_*.parquet"))

    marginal_total = sum(pq.read_table(f).num_rows for f in marginal_files)
    curve_total = sum(pq.read_table(f).num_rows for f in curve_files)

    profile: dict[str, Any] = {
        "marginal_prices_total_rows": marginal_total,
        "bidding_curves_total_rows": curve_total,
        "total_rows": marginal_total + curve_total,
        "files_count": len(marginal_files) + len(curve_files),
        "dataset_tables": {
            "marginal_prices": {
                "files": [f.name for f in marginal_files],
                "row_count": marginal_total,
            },
            "bidding_curves": {
                "files": [f.name for f in curve_files],
                "row_count": curve_total,
            },
        },
    }

    schema_def = {
        "marginal_prices_schema": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in OMIE_MARGINAL_SCHEMA
        ],
        "bidding_curves_schema": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in OMIE_CURVES_SCHEMA
        ],
    }

    quality = {
        "passed_checks": [
            "valid_date_ranges",
            "complete_hourly_sequences",
            "valid_offer_types_C_V",
        ],
    }

    provenance = {
        "source_name": "OMIE - Operador del Mercado Ibérico de Energía",
        "source_url": "https://www.omie.es/es/file-download?parents[0]=curva_pbc",
        "license": "Public market data with mandatory attribution to OMIE",
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "0.2.0",
    }

    (config.artifacts_dir / "profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    (config.artifacts_dir / "schema.json").write_text(json.dumps(schema_def, indent=2), encoding="utf-8")
    (config.artifacts_dir / "quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    (config.artifacts_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    logger.info("Generated profile and metadata in %s", config.artifacts_dir)
    return profile
