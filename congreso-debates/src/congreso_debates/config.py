from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Config:
    legislatures: list[int] = field(default_factory=lambda: list(range(1, 16)))
    max_sessions_per_leg: int | None = None
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    artifacts_dir: Path = Path("artifacts")
    staging_dir: Path = Path("hf_staging")
    download_speech_pdfs: bool = True
    max_speech_pdfs: int | None = None
    request_delay_seconds: float = 0.01
    timeout_seconds: int = 45
    max_retries: int = 3
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    @classmethod
    def load(cls, path: Path | str) -> Config:
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text(encoding="utf-8"))
        for k in ("raw_dir", "processed_dir", "artifacts_dir", "staging_dir"):
            if k in data:
                data[k] = Path(data[k])
        config = cls(**data)
        config.validate()
        return config

    def validate(self) -> None:
        if self.max_sessions_per_leg is not None and self.max_sessions_per_leg < 1:
            raise ValueError("max_sessions_per_leg must be >= 1 or null")
        if self.max_speech_pdfs is not None and self.max_speech_pdfs < 1:
            raise ValueError("max_speech_pdfs must be >= 1 or null")
        if self.request_delay_seconds < 0:
            raise ValueError("request_delay_seconds cannot be negative")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")
        if not self.legislatures:
            raise ValueError("legislatures list cannot be empty")
