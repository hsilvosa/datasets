from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


COLUMNS = [
    "code", "product_name", "generic_name", "brands", "quantity", "categories",
    "ingredients_text", "allergens", "labels", "countries", "packaging",
    "created_datetime", "last_modified_datetime", "nutriments_json", "source_json",
]
SCHEMA = pa.schema([(name, pa.string()) for name in COLUMNS[:-2]] + [("nutriments_json", pa.string()), ("source_json", pa.string())])


def clean(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def transform(product: dict) -> dict:
    return {
        "code": clean(product.get("code")), "product_name": clean(product.get("product_name")),
        "generic_name": clean(product.get("generic_name")), "brands": clean(product.get("brands")),
        "quantity": clean(product.get("quantity")), "categories": clean(product.get("categories")),
        "ingredients_text": clean(product.get("ingredients_text")), "allergens": clean(product.get("allergens")),
        "labels": clean(product.get("labels")), "countries": clean(product.get("countries")),
        "packaging": clean(product.get("packaging")), "created_datetime": clean(product.get("created_datetime")),
        "last_modified_datetime": clean(product.get("last_modified_datetime")),
        "nutriments_json": clean(product.get("nutriments")),
        "source_json": json.dumps(product, ensure_ascii=False, separators=(",", ":")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--output", default="data/processed/products.parquet")
    parser.add_argument("--batch-rows", type=int, default=50_000)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cfg = json.loads((root / args.config).read_text(encoding="utf-8"))
    source = root / "data/raw" / cfg["snapshot_date"] / cfg["filename"]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    rows, seen = [], 0
    with pq.ParquetWriter(output, SCHEMA, compression="zstd") as writer, gzip.open(source, "rt", encoding="utf-8") as handle:
        for line in handle:
            rows.append(transform(json.loads(line)))
            seen += 1
            if len(rows) >= args.batch_rows:
                writer.write_table(pa.Table.from_pylist(rows, schema=SCHEMA)); rows.clear()
            if args.limit and seen >= args.limit:
                break
        if rows:
            writer.write_table(pa.Table.from_pylist(rows, schema=SCHEMA))


if __name__ == "__main__":
    main()
