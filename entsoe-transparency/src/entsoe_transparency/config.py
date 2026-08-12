from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    country_code: str
    eic_code: str
    valid_from: str | None = None
    valid_to: str | None = None


@dataclass(frozen=True)
class Config:
    base_url: str
    token_env: str
    env_file: Path
    zones_file: Path
    raw_dir: Path
    processed_dir: Path
    artifacts_dir: Path
    staging_dir: Path
    start_date: str
    end_date: str
    datasets: list[str]
    zone_keys: list[str] | None
    price_chunk_months: int
    load_chunk_months: int
    max_workers: int
    requests_per_second: float
    timeout_seconds: int
    max_retries: int
    parquet_rows_per_file: int
    max_tasks: int | None
    user_agent: str

    @classmethod
    def load(cls, path: Path) -> Config:
        path = path.resolve()
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        known = {field.name for field in fields(cls)}
        unknown = sorted(set(payload) - known)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {', '.join(unknown)}")
        base = path.parent.parent
        for key in ("env_file", "zones_file", "raw_dir", "processed_dir", "artifacts_dir", "staging_dir"):
            value = Path(payload[key])
            payload[key] = value if value.is_absolute() else (base / value).resolve()
        config = cls(**payload)
        config.validate()
        return config

    def validate(self) -> None:
        start = date.fromisoformat(self.start_date)
        end = date.fromisoformat(self.end_date)
        if end <= start:
            raise ValueError("end_date must be later than start_date")
        supported = {"day_ahead_prices", "actual_load"}
        invalid = sorted(set(self.datasets) - supported)
        if invalid:
            raise ValueError(f"Unsupported datasets: {', '.join(invalid)}")
        if self.max_workers < 1 or self.max_workers > 16:
            raise ValueError("max_workers must be between 1 and 16")
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if self.price_chunk_months < 1 or self.load_chunk_months < 1:
            raise ValueError("chunk sizes must be positive")

    def zones(self) -> list[Zone]:
        payload = json.loads(self.zones_file.read_text(encoding="utf-8"))
        zones = [Zone(**item) for item in payload]
        if self.zone_keys is not None:
            requested = set(self.zone_keys)
            found = {zone.key for zone in zones}
            missing = sorted(requested - found)
            if missing:
                raise ValueError(f"Unknown zone keys: {', '.join(missing)}")
            zones = [zone for zone in zones if zone.key in requested]
        return zones

    def public_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field in fields(self):
            if field.name in {"token_env", "env_file"}:
                continue
            value = getattr(self, field.name)
            result[field.name] = str(value) if isinstance(value, Path) else value
        return result
