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
    start_year: int
    end_year: int
    end_month: int
    monthly_from_year: int
    max_archives: int | None
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
        if self.start_year < 2012 or self.end_year < self.start_year:
            raise ValueError("The supported historical range starts in 2012")
        if not 1 <= self.end_month <= 12:
            raise ValueError("end_month must be between 1 and 12")
        if not self.start_year <= self.monthly_from_year <= self.end_year + 1:
            raise ValueError("monthly_from_year must be inside or immediately after the year range")
        if self.max_archives is not None and self.max_archives < 1:
            raise ValueError("max_archives must be positive or null")
        if self.timeout_seconds < 1 or self.max_retries < 0:
            raise ValueError("Invalid HTTP retry configuration")
        if self.parquet_rows_per_file < 1:
            raise ValueError("parquet_rows_per_file must be positive")

    def public_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            result[field.name] = str(value) if isinstance(value, Path) else value
        return result
