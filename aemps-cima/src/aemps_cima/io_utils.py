from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
        handle.flush()
    return count


def write_jsonl_atomic(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    count = 0
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                count += 1
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return count


def repair_jsonl(path: Path, unique_key: str) -> dict[str, int]:
    """Atomically remove malformed lines and duplicate keyed records from a JSONL file."""
    if not path.exists():
        return {"valid": 0, "duplicates": 0, "malformed": 0}
    temporary = path.with_suffix(path.suffix + ".repair")
    seen = set()
    counts = {"valid": 0, "duplicates": 0, "malformed": 0}
    try:
        with (
            path.open("r", encoding="utf-8") as source,
            temporary.open("w", encoding="utf-8", newline="\n") as target,
        ):
            for line in source:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    counts["malformed"] += 1
                    continue
                identifier = str(row.get(unique_key))
                if identifier in seen:
                    counts["duplicates"] += 1
                    continue
                seen.add(identifier)
                target.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                counts["valid"] += 1
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return counts


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {path}:{line_number}") from exc


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
