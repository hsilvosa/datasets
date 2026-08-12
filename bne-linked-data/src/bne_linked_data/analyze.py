from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from .config import Config
from .io_utils import sha256_file, write_json


def _sql_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def _profile_collection(config: Config, name: str, sources: list[Path]) -> dict[str, object]:
    pattern = _sql_path(config.processed_dir / name / "*.parquet")
    connection = duckdb.connect()
    try:
        row = connection.execute(
            f"""
            SELECT
                count(*) AS rows,
                count(DISTINCT subject) AS distinct_subjects,
                count(DISTINCT predicate) AS distinct_predicates,
                count(DISTINCT object) AS distinct_objects,
                count(*) FILTER (WHERE object_kind = 'iri') AS iri_objects,
                count(*) FILTER (WHERE object_kind = 'literal') AS literal_objects,
                count(*) FILTER (WHERE object_kind = 'blank_node') AS blank_node_objects,
                count(*) FILTER (WHERE language IS NOT NULL) AS language_tagged_literals,
                count(*) FILTER (WHERE datatype IS NOT NULL) AS typed_literals,
                min(source_line) AS first_source_line,
                max(source_line) AS last_source_line
            FROM read_parquet('{pattern}')
            """
        ).fetchone()
        languages = connection.execute(
            f"""
            SELECT language, count(*) AS rows
            FROM read_parquet('{pattern}')
            WHERE language IS NOT NULL
            GROUP BY language ORDER BY rows DESC, language LIMIT 30
            """
        ).fetchall()
        predicates = connection.execute(
            f"""
            SELECT predicate, count(*) AS rows
            FROM read_parquet('{pattern}')
            GROUP BY predicate ORDER BY rows DESC, predicate LIMIT 30
            """
        ).fetchall()
    finally:
        connection.close()
    keys = (
        "rows",
        "distinct_subjects",
        "distinct_predicates",
        "distinct_objects",
        "iri_objects",
        "literal_objects",
        "blank_node_objects",
        "language_tagged_literals",
        "typed_literals",
        "first_source_line",
        "last_source_line",
    )
    result = dict(zip(keys, row, strict=True))
    result.update(
        {
            "parquet_files": len(sources),
            "parquet_bytes": sum(path.stat().st_size for path in sources),
            "languages": [{"language": key, "rows": count} for key, count in languages],
            "top_predicates": [
                {"predicate": predicate, "rows": count} for predicate, count in predicates
            ],
        }
    )
    return result


def analyze(config: Config) -> dict[str, object]:
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    profiles: dict[str, dict[str, object]] = {}
    parquet_sources: list[Path] = []
    for collection in config.collections:
        sources = sorted(config.processed_path(collection).glob("*.parquet"))
        if not sources:
            continue
        parquet_sources.extend(sources)
        profiles[collection.name] = _profile_collection(config, collection.name, sources)
    if not profiles:
        raise FileNotFoundError(f"No Parquet files found under {config.processed_dir}")
    profile = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "snapshot_date": config.snapshot_date,
        "sample_limited": config.max_triples_per_collection is not None,
        "collections": profiles,
        "totals": {
            "rows": sum(int(item["rows"]) for item in profiles.values()),
            "parquet_files": len(parquet_sources),
            "parquet_bytes": sum(path.stat().st_size for path in parquet_sources),
        },
    }
    schema = {
        "format": "Parquet",
        "tables": {
            name: [
                {"name": field.name, "type": str(field.type), "nullable": field.nullable}
                for field in pq.read_schema(sources[0])
            ]
            for name in profiles
            for sources in [sorted((config.processed_dir / name).glob("*.parquet"))]
        },
        "semantics": {
            "record_id": "Stable collection and source-line identifier within this snapshot",
            "subject": "Decoded N-Triples subject IRI or blank-node identifier",
            "predicate": "Decoded predicate IRI",
            "object": "Decoded IRI, blank-node identifier, or literal lexical value",
            "object_kind": "One of iri, literal, or blank_node",
            "language": "BCP 47 language tag when present on a literal",
            "datatype": "Datatype IRI when present on a literal",
            "source_line": "One-based line number in the decompressed official dump",
        },
    }
    normalization_path = config.artifacts_dir / "normalization.json"
    normalization = (
        json.loads(normalization_path.read_text(encoding="utf-8"))
        if normalization_path.exists()
        else {"collections": []}
    )
    normalization_by_name = {
        item["collection"]: item for item in normalization.get("collections", [])
    }
    quality_checks = {
        name: {
                "non_empty": int(item["rows"]) > 0,
                "subject_count_positive": int(item["distinct_subjects"]) > 0,
                "predicate_count_positive": int(item["distinct_predicates"]) > 0,
                "object_kinds_sum_to_rows": sum(
                    int(item[key])
                    for key in ("iri_objects", "literal_objects", "blank_node_objects")
                )
                == int(item["rows"]),
                "normalization_rows_match": name in normalization_by_name
                and int(normalization_by_name[name]["parsed_triples"]) == int(item["rows"]),
                "no_invalid_source_lines": name in normalization_by_name
                and int(normalization_by_name[name]["invalid_lines"]) == 0,
            }
        for name, item in profiles.items()
    }
    quality = {
        "passed": all(all(checks.values()) for checks in quality_checks.values()),
        "checks": quality_checks,
    }
    provenance = {
        "publisher": "Biblioteca Nacional de España",
        "source_portal": "https://datos.bne.es/",
        "documentation": "https://www.bne.es/es/catalogos/datos-enlazados-bne/datos-enlazados",
        "license": "CC0-1.0",
        "snapshot_date": config.snapshot_date,
        "source_files": [
            {
                "collection": item.name,
                "url": item.url,
                "filename": item.filename,
                "expected_bytes": item.expected_bytes,
                "note": item.note,
            }
            for item in config.collections
        ],
        "transformations": [
            "Stream-decompress BZip2 without loading the full graph into memory",
            "Rejoin external IRIs split across two physical lines by the BNE subjects dump",
            "Parse each N-Triples statement into explicit subject, predicate, and object fields",
            "Preserve language tags, datatype IRIs, blank nodes, collection, and source line",
            "Write compressed Parquet shards without resampling, inference, or enrichment",
        ],
    }
    checksums = {
        str(path.relative_to(config.project_root)).replace("\\", "/"): {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in parquet_sources
    }
    for name, value in (
        ("profile.json", profile),
        ("schema.json", schema),
        ("quality.json", quality),
        ("provenance.json", provenance),
        ("checksums.json", checksums),
    ):
        write_json(config.artifacts_dir / name, value)
    return profile
