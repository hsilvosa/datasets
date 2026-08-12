from __future__ import annotations

import bz2
import datetime as dt
import shutil
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .config import Collection, Config
from .io_utils import write_json
from .rdf_parser import Triple, parse_ntriples_line

SCHEMA = pa.schema(
    [
        ("record_id", pa.string()),
        ("subject", pa.string()),
        ("predicate", pa.string()),
        ("object", pa.string()),
        ("object_kind", pa.dictionary(pa.int8(), pa.string())),
        ("language", pa.dictionary(pa.int16(), pa.string())),
        ("datatype", pa.string()),
        ("collection", pa.dictionary(pa.int8(), pa.string())),
        ("source_line", pa.uint64()),
        ("snapshot_date", pa.date32()),
    ]
)


def _row(collection: Collection, snapshot_date: str, line_number: int, triple: Triple) -> dict:
    return {
        "record_id": f"{collection.name}:{line_number}",
        "subject": triple.subject,
        "predicate": triple.predicate,
        "object": triple.object,
        "object_kind": triple.object_kind,
        "language": triple.language,
        "datatype": triple.datatype,
        "collection": collection.name,
        "source_line": line_number,
        "snapshot_date": dt.date.fromisoformat(snapshot_date),
    }


def _write_shard(rows: list[dict], target: Path, index: int) -> Path:
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    path = target / f"train-{index:05d}.parquet"
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=9,
        use_dictionary=True,
        write_statistics=True,
    )
    return path


def normalize_collection(config: Config, collection: Collection) -> dict[str, object]:
    source = config.raw_path(collection)
    if not source.exists():
        raise FileNotFoundError(f"Missing source dump: {source}")
    target = config.processed_path(collection)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    started = time.perf_counter()
    rows: list[dict] = []
    shards: list[Path] = []
    parsed = 0
    ignored = 0
    invalid = 0
    repaired_wrapped_iris = 0
    examples: list[dict[str, object]] = []
    pending_line: str | None = None
    pending_line_number: int | None = None
    opener = bz2.open if source.suffix == ".bz2" else Path.open
    with opener(source, mode="rt", encoding="utf-8", errors="strict", newline="") as handle:
        for line_number, line in enumerate(handle, start=1):
            logical_line_number = line_number
            if pending_line is not None:
                if line.lstrip().startswith(">"):
                    line = pending_line.rstrip("\r\n") + line.lstrip()
                    logical_line_number = int(pending_line_number)
                    repaired_wrapped_iris += 1
                    pending_line = None
                    pending_line_number = None
                else:
                    invalid += 1
                    if len(examples) < 20:
                        examples.append(
                            {
                                "line": pending_line_number,
                                "error": "Unterminated IRI was not continued on the next line",
                            }
                        )
                    pending_line = None
                    pending_line_number = None
            try:
                triple = parse_ntriples_line(line)
            except (UnicodeError, ValueError) as exc:
                stripped = line.rstrip("\r\n")
                if (
                    str(exc) == "Triple must end with a period"
                    and stripped.count("<") > stripped.count(">")
                ):
                    pending_line = line
                    pending_line_number = logical_line_number
                    continue
                invalid += 1
                if len(examples) < 20:
                    examples.append({"line": logical_line_number, "error": str(exc)})
                continue
            if triple is None:
                ignored += 1
                continue
            rows.append(_row(collection, config.snapshot_date, logical_line_number, triple))
            parsed += 1
            if len(rows) >= config.chunk_rows:
                shards.append(_write_shard(rows, target, len(shards)))
                rows.clear()
            if config.max_triples_per_collection and parsed >= config.max_triples_per_collection:
                break
    if pending_line is not None:
        invalid += 1
        if len(examples) < 20:
            examples.append(
                {"line": pending_line_number, "error": "Unterminated IRI at end of source"}
            )
    if rows:
        shards.append(_write_shard(rows, target, len(shards)))
    return {
        "collection": collection.name,
        "source": str(source),
        "parsed_triples": parsed,
        "ignored_lines": ignored,
        "invalid_lines": invalid,
        "repaired_wrapped_iris": repaired_wrapped_iris,
        "invalid_examples": examples,
        "shards": len(shards),
        "parquet_bytes": sum(path.stat().st_size for path in shards),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "limited": config.max_triples_per_collection is not None,
    }


def normalize(config: Config) -> dict[str, object]:
    config.processed_dir.mkdir(parents=True, exist_ok=True)
    collections = [normalize_collection(config, item) for item in config.collections]
    result = {
        "snapshot_date": config.snapshot_date,
        "collections": collections,
        "total_triples": sum(int(item["parsed_triples"]) for item in collections),
        "invalid_lines": sum(int(item["invalid_lines"]) for item in collections),
        "repaired_wrapped_iris": sum(
            int(item["repaired_wrapped_iris"]) for item in collections
        ),
        "parquet_bytes": sum(int(item["parquet_bytes"]) for item in collections),
    }
    write_json(config.artifacts_dir / "normalization.json", result)
    return result
