from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    download_url: str
    raw_dir: Path
    processed_dir: Path
    artifacts_dir: Path
    staging_dir: Path
    start_date: str
    end_date: str
    latitude_min: float = 26.0
    latitude_max: float = 45.0
    longitude_min: float = -20.0
    longitude_max: float = 6.0
    max_rows: int | None = None
    parquet_rows_per_file: int = 100_000
    shard_years: int | None = None
    coalesce_before_year: int | None = None
    annual_shard_ranges: list[list[int]] | None = None
    monthly_shard_years: list[int] | None = None
    daily_shard_months: list[list[int]] | None = None
    html_fallback_files: list[str] | None = None
    expected_min_rows: int | None = None
    request_delay_seconds: float = 0.2
    timeout_seconds: int = 60
    max_retries: int = 3
    user_agent: str = "public-data-research-ign-earthquakes/0.1"

    @classmethod
    def load(cls, path: str | Path) -> Config:
        config_path = Path(path).resolve()
        payload: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
        allowed = {item.name for item in fields(cls)}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {', '.join(unknown)}")
        base = config_path.parent.parent
        for key in ("raw_dir", "processed_dir", "artifacts_dir", "staging_dir"):
            value = Path(payload[key])
            payload[key] = value if value.is_absolute() else (base / value).resolve()
        config = cls(**payload)
        config.validate()
        return config

    def validate(self) -> None:
        start = datetime.strptime(self.start_date, "%d/%m/%Y").replace(tzinfo=UTC).date()
        end = datetime.strptime(self.end_date, "%d/%m/%Y").replace(tzinfo=UTC).date()
        if end < start:
            raise ValueError("end_date must not be before start_date")
        if self.latitude_min >= self.latitude_max:
            raise ValueError("latitude_min must be below latitude_max")
        if self.longitude_min >= self.longitude_max:
            raise ValueError("longitude_min must be below longitude_max")
        if self.max_rows is not None and self.max_rows < 1:
            raise ValueError("max_rows must be positive or null")
        if self.parquet_rows_per_file < 1:
            raise ValueError("parquet_rows_per_file must be positive")
        if self.shard_years is not None and self.shard_years < 1:
            raise ValueError("shard_years must be positive or null")
        if self.coalesce_before_year is not None and self.coalesce_before_year < 1:
            raise ValueError("coalesce_before_year must be positive or null")
        for bounds in self.annual_shard_ranges or []:
            if len(bounds) != 2 or bounds[0] > bounds[1]:
                raise ValueError("annual_shard_ranges must contain [start_year, end_year]")
        for year_month in self.daily_shard_months or []:
            if len(year_month) != 2 or not 1 <= year_month[1] <= 12:
                raise ValueError("daily_shard_months must contain [year, month]")
        if self.expected_min_rows is not None and self.expected_min_rows < 0:
            raise ValueError("expected_min_rows must be non-negative or null")
