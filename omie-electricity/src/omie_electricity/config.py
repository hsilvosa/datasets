from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    start_date: str
    end_date: str
    raw_dir: Path
    processed_dir: Path
    artifacts_dir: Path
    staging_dir: Path
    include_curves: bool = True
    request_delay_seconds: float = 0.05
    timeout_seconds: int = 30
    max_retries: int = 3
    user_agent: str = "public-data-research-omie-electricity/0.1"

    @property
    def parsed_start_date(self) -> date:
        return datetime.strptime(self.start_date, "%Y-%m-%d").date()

    @property
    def parsed_end_date(self) -> date:
        return datetime.strptime(self.end_date, "%Y-%m-%d").date()

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
        if self.parsed_end_date < self.parsed_start_date:
            raise ValueError("end_date must not be before start_date")
        if self.request_delay_seconds < 0:
            raise ValueError("request_delay_seconds cannot be negative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
