from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    base_url: str
    raw_dir: Path
    processed_dir: Path
    artifacts_dir: Path
    staging_dir: Path
    request_delay_seconds: float = 0.2
    max_workers: int = 4
    timeout_seconds: int = 60
    max_retries: int = 5
    max_pages: int | None = None
    max_medications: int | None = None
    include_details: bool = True
    include_documents: bool = True
    include_change_register: bool = True
    change_register_workers: int = 4
    changes_since: str = "01/01/2000"
    parquet_rows_per_file: int = 100_000
    user_agent: str = "public-data-research-cima/0.1"

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
        return cls(**payload)
