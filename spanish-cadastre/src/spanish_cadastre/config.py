from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    raw_dir: Path
    processed_dir: Path
    artifacts_dir: Path
    staging_dir: Path
    collections: list[str]
    municipality_codes: list[str] | None
    max_municipalities: int | None
    max_workers: int
    request_delay_seconds: float
    timeout_seconds: int
    max_retries: int
    parquet_rows_per_file: int
    user_agent: str

    @classmethod
    def load(cls, path: str | Path) -> Config:
        config_path = Path(path).resolve()
        payload: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
        allowed = {field.name for field in fields(cls)}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {', '.join(unknown)}")
        root = config_path.parent.parent
        for key in ("raw_dir", "processed_dir", "artifacts_dir", "staging_dir"):
            value = Path(payload[key])
            payload[key] = value if value.is_absolute() else (root / value).resolve()
        config = cls(**payload)
        config.validate()
        return config

    def validate(self) -> None:
        supported = {"parcels", "addresses", "buildings"}
        invalid = sorted(set(self.collections) - supported)
        if invalid or not self.collections:
            raise ValueError(f"Unsupported or empty collections: {', '.join(invalid)}")
        if self.max_workers < 1 or self.max_workers > 4:
            raise ValueError("max_workers must be between 1 and 4")
        if self.request_delay_seconds < 0 or self.timeout_seconds < 1 or self.max_retries < 0:
            raise ValueError("Invalid HTTP configuration")
        if self.max_municipalities is not None and self.max_municipalities < 1:
            raise ValueError("max_municipalities must be positive or null")
        if self.parquet_rows_per_file < 1:
            raise ValueError("parquet_rows_per_file must be positive")

    def public_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            result[field.name] = str(value) if isinstance(value, Path) else value
        return result
