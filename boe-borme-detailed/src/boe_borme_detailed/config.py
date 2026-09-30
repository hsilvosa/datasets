from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    base_processed_dir: Path
    processed_dir: Path
    artifacts_dir: Path
    state_dir: Path
    staging_dir: Path
    base_dataset: str = "hsilvosa/boe-borme"
    shard_objects: int = 250
    expected_min_rows: int | None = None
    user_agent: str = "public-data-research-boe-borme-detailed/0.1"

    @classmethod
    def load(cls, path: str | Path) -> Config:
        config_path = Path(path).resolve()
        payload: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
        allowed = {item.name for item in fields(cls)}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {', '.join(unknown)}")
        base = config_path.parent.parent
        for key in (
            "base_processed_dir",
            "processed_dir",
            "artifacts_dir",
            "state_dir",
            "staging_dir",
        ):
            value = Path(payload[key])
            payload[key] = value if value.is_absolute() else (base / value).resolve()
        config = cls(**payload)
        config.validate()
        return config

    def validate(self) -> None:
        if self.shard_objects < 1:
            raise ValueError("shard_objects must be positive")
        if self.expected_min_rows is not None and self.expected_min_rows < 0:
            raise ValueError("expected_min_rows must be non-negative or null")
        if self.processed_dir == self.base_processed_dir:
            raise ValueError("processed_dir must differ from base_processed_dir")

    def base_table_dir(self, table: str) -> Path:
        return self.base_processed_dir / table
