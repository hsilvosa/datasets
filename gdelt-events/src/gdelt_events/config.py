from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    raw_dir: Path
    artifacts_dir: Path
    base_url: str
    snapshot_date: date
    workers: int
    timeout_seconds: int
    max_retries: int
    chunk_size: int
    user_agent: str
    max_files: int | None

    @classmethod
    def load(cls, path: str | Path) -> Config:
        config_path = Path(path).resolve()
        payload: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
        allowed = {field.name for field in fields(cls)}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {', '.join(unknown)}")
        root = config_path.parent.parent
        for key in ("raw_dir", "artifacts_dir"):
            value = Path(payload[key])
            payload[key] = value if value.is_absolute() else (root / value).resolve()
        payload["snapshot_date"] = date.fromisoformat(payload["snapshot_date"])
        config = cls(**payload)
        config.validate()
        return config

    def validate(self) -> None:
        if self.snapshot_date < date(2013, 4, 1):
            raise ValueError("snapshot_date must be on or after 2013-04-01")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be HTTP or HTTPS")
        if self.workers < 1 or self.workers > 32:
            raise ValueError("workers must be between 1 and 32")
        if self.timeout_seconds < 1 or self.max_retries < 0 or self.chunk_size < 1:
            raise ValueError("Invalid download configuration")
        if self.max_files is not None and self.max_files < 1:
            raise ValueError("max_files must be positive or null")
