from __future__ import annotations

import argparse
import bz2
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


SCHEMAS = {
    "entities": pa.schema([("entity_id", pa.string()), ("entity_type", pa.string()), ("modified", pa.string()), ("last_revision_id", pa.int64())]),
    "terms": pa.schema([("entity_id", pa.string()), ("term_type", pa.string()), ("language", pa.string()), ("value", pa.string())]),
    "sitelinks": pa.schema([("entity_id", pa.string()), ("site", pa.string()), ("title", pa.string()), ("badges_json", pa.string())]),
    "claims": pa.schema([("entity_id", pa.string()), ("property_id", pa.string()), ("statement_id", pa.string()), ("rank", pa.string()), ("mainsnak_json", pa.string()), ("qualifiers_json", pa.string()), ("references_json", pa.string())]),
}


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def transform(entity: dict) -> dict[str, list[dict]]:
    entity_id = entity["id"]
    result = {name: [] for name in SCHEMAS}
    result["entities"].append({"entity_id": entity_id, "entity_type": entity.get("type", ""), "modified": entity.get("modified", ""), "last_revision_id": entity.get("lastrevid")})
    for term_type in ("labels", "descriptions"):
        for language, term in entity.get(term_type, {}).items():
            result["terms"].append({"entity_id": entity_id, "term_type": term_type[:-1], "language": language, "value": term.get("value", "")})
    for language, aliases in entity.get("aliases", {}).items():
        for term in aliases:
            result["terms"].append({"entity_id": entity_id, "term_type": "alias", "language": language, "value": term.get("value", "")})
    for site, link in entity.get("sitelinks", {}).items():
        result["sitelinks"].append({"entity_id": entity_id, "site": site, "title": link.get("title", ""), "badges_json": compact(link.get("badges", []))})
    for property_id, statements in entity.get("claims", {}).items():
        for statement in statements:
            result["claims"].append({"entity_id": entity_id, "property_id": property_id, "statement_id": statement.get("id", ""), "rank": statement.get("rank", ""), "mainsnak_json": compact(statement.get("mainsnak")), "qualifiers_json": compact(statement.get("qualifiers", {})), "references_json": compact(statement.get("references", []))})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--output-dir", default="data/processed")
    parser.add_argument("--batch-entities", type=int, default=25_000)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cfg = json.loads((root / args.config).read_text(encoding="utf-8"))
    source = root / "data/raw" / cfg["snapshot_date"] / cfg["filename"]
    output = root / args.output_dir; output.mkdir(parents=True, exist_ok=True)
    writers = {name: pq.ParquetWriter(output / f"{name}.parquet", schema, compression="zstd") for name, schema in SCHEMAS.items()}
    batches = {name: [] for name in SCHEMAS}; seen = 0
    try:
        with bz2.open(source, "rt", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip().rstrip(",")
                if text in ("[", "]", ""):
                    continue
                for name, rows in transform(json.loads(text)).items(): batches[name].extend(rows)
                seen += 1
                if seen % args.batch_entities == 0:
                    for name, rows in batches.items():
                        if rows: writers[name].write_table(pa.Table.from_pylist(rows, schema=SCHEMAS[name])); rows.clear()
                if args.limit and seen >= args.limit: break
        for name, rows in batches.items():
            if rows: writers[name].write_table(pa.Table.from_pylist(rows, schema=SCHEMAS[name]))
    finally:
        for writer in writers.values(): writer.close()


if __name__ == "__main__":
    main()
