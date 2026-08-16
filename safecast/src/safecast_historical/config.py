from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    archive_path: Path
    processed_dir: Path
    artifacts_dir: Path
    staging_dir: Path
    rows_per_file: int
    csv_block_size: int

    @classmethod
    def load(cls, path: str | Path) -> Config:
        config_path = Path(path).resolve()
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        root = config_path.parent.parent
        for name in ("archive_path", "processed_dir", "artifacts_dir", "staging_dir"):
            value = Path(payload[name])
            payload[name] = value if value.is_absolute() else (root / value).resolve()
        config = cls(**payload)
        if config.rows_per_file < 1 or config.csv_block_size < 1024:
            raise ValueError("Invalid output or CSV block size")
        return config

    def public_dict(self) -> dict:
        return {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(self).items()
        }
