from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    raw_dir: Path
    processed_dir: Path
    artifacts_dir: Path
    state_dir: Path
    staging_dir: Path
    boe_start_date: str = "1960-09-01"
    borme_start_date: str = "2009-01-01"
    end_date: str | None = None
    include_boe_sumario: bool = True
    include_borme_sumario: bool = True
    include_legislacion: bool = True
    include_legislacion_texto: bool = True
    include_aux: bool = True
    refresh_days: int = 7
    max_units: int | None = None
    max_workers: int = 4
    request_delay_seconds: float = 0.3
    timeout_seconds: int = 120
    max_retries: int = 5
    parquet_rows_per_file: int = 100_000
    shard_objects: int = 250
    base_url: str = "https://www.boe.es"
    expected_min_rows: int | None = None
    user_agent: str = "public-data-research-boe-borme/0.1 (research dataset builder)"

    @classmethod
    def load(cls, path: str | Path) -> Config:
        config_path = Path(path).resolve()
        payload: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
        allowed = {item.name for item in fields(cls)}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {', '.join(unknown)}")
        base = config_path.parent.parent
        for key in ("raw_dir", "processed_dir", "artifacts_dir", "state_dir", "staging_dir"):
            value = Path(payload[key])
            payload[key] = value if value.is_absolute() else (base / value).resolve()
        config = cls(**payload)
        config.validate()
        return config

    @property
    def resolved_end_date(self) -> str:
        return self.end_date or datetime.now(UTC).date().isoformat()

    def start_for(self, dataset: str) -> date:
        raw = self.boe_start_date if dataset == "boe_sumario" else self.borme_start_date
        return date.fromisoformat(raw)

    def end(self) -> date:
        return date.fromisoformat(self.resolved_end_date)

    def validate(self) -> None:
        for name, value in (
            ("boe_start_date", self.boe_start_date),
            ("borme_start_date", self.borme_start_date),
        ):
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{name} must use YYYY-MM-DD") from exc
        if self.end_date is not None:
            try:
                date.fromisoformat(self.end_date)
            except ValueError as exc:
                raise ValueError("end_date must use YYYY-MM-DD") from exc
            if self.end() < self.start_for("boe_sumario"):
                raise ValueError("end_date must not be before boe_start_date")
        if self.end_date is not None and self.end() < self.start_for("borme_sumario"):
            raise ValueError("end_date must not be before borme_start_date")
        if self.refresh_days < 0:
            raise ValueError("refresh_days must be non-negative")
        if self.max_workers < 1:
            raise ValueError("max_workers must be positive")
        if self.request_delay_seconds < 0:
            raise ValueError("request_delay_seconds must be non-negative")
        if self.parquet_rows_per_file < 1:
            raise ValueError("parquet_rows_per_file must be positive")
        if self.shard_objects < 1:
            raise ValueError("shard_objects must be positive")
        if self.max_units is not None and self.max_units < 1:
            raise ValueError("max_units must be positive or null")
        if self.expected_min_rows is not None and self.expected_min_rows < 0:
            raise ValueError("expected_min_rows must be non-negative or null")
