from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Collection:
    name: str
    url: str
    filename: str
    expected_bytes: int
    note: str | None = None
    local_path: str | None = None


@dataclass(frozen=True)
class Config:
    config_path: Path
    project_root: Path
    snapshot_date: str
    raw_dir: Path
    processed_dir: Path
    artifacts_dir: Path
    staging_dir: Path
    chunk_rows: int
    max_triples_per_collection: int | None
    timeout_seconds: int
    retries: int
    collections: tuple[Collection, ...]

    @classmethod
    def load(cls, path: Path) -> Config:
        config_path = path.resolve()
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        project_root = config_path.parent.parent

        def project_path(value: str) -> Path:
            candidate = Path(value)
            return candidate if candidate.is_absolute() else project_root / candidate

        collections = tuple(Collection(**item) for item in payload["collections"])
        if not collections:
            raise ValueError("At least one collection is required")
        names = [item.name for item in collections]
        if len(names) != len(set(names)):
            raise ValueError("Collection names must be unique")
        chunk_rows = int(payload.get("chunk_rows", 250_000))
        if chunk_rows <= 0:
            raise ValueError("chunk_rows must be positive")
        maximum = payload.get("max_triples_per_collection")
        if maximum is not None and int(maximum) <= 0:
            raise ValueError("max_triples_per_collection must be positive or null")
        return cls(
            config_path=config_path,
            project_root=project_root,
            snapshot_date=str(payload["snapshot_date"]),
            raw_dir=project_path(payload["raw_dir"]),
            processed_dir=project_path(payload["processed_dir"]),
            artifacts_dir=project_path(payload["artifacts_dir"]),
            staging_dir=project_path(payload["staging_dir"]),
            chunk_rows=chunk_rows,
            max_triples_per_collection=None if maximum is None else int(maximum),
            timeout_seconds=int(payload.get("timeout_seconds", 90)),
            retries=int(payload.get("retries", 5)),
            collections=collections,
        )

    def raw_path(self, collection: Collection) -> Path:
        return self.raw_dir / collection.filename

    def processed_path(self, collection: Collection) -> Path:
        return self.processed_dir / collection.name
