from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

try:
    import osmium
except ImportError as exc:
    raise SystemExit("Install pyosmium before processing the full-history PBF") from exc


OBJECT_SCHEMA = pa.schema([("object_type", pa.string()), ("object_id", pa.int64()), ("version", pa.int32()), ("visible", pa.bool_()), ("timestamp", pa.string()), ("changeset", pa.int64()), ("uid", pa.int64()), ("user", pa.string()), ("longitude", pa.float64()), ("latitude", pa.float64())])
TAG_SCHEMA = pa.schema([("object_type", pa.string()), ("object_id", pa.int64()), ("version", pa.int32()), ("key", pa.string()), ("value", pa.string())])
WAY_SCHEMA = pa.schema([("way_id", pa.int64()), ("version", pa.int32()), ("position", pa.int32()), ("node_id", pa.int64())])
MEMBER_SCHEMA = pa.schema([("relation_id", pa.int64()), ("version", pa.int32()), ("position", pa.int32()), ("member_type", pa.string()), ("member_id", pa.int64()), ("role", pa.string())])


class Handler(osmium.SimpleHandler):
    def __init__(self, output: Path, batch_rows: int, limit: int | None):
        super().__init__(); output.mkdir(parents=True, exist_ok=True)
        self.batch_rows, self.limit, self.seen = batch_rows, limit, 0
        self.rows = {"objects": [], "tags": [], "way_nodes": [], "relation_members": []}
        self.schemas = {"objects": OBJECT_SCHEMA, "tags": TAG_SCHEMA, "way_nodes": WAY_SCHEMA, "relation_members": MEMBER_SCHEMA}
        self.writers = {name: pq.ParquetWriter(output / f"{name}.parquet", schema, compression="zstd") for name, schema in self.schemas.items()}

    def common(self, obj, kind: str, lon=None, lat=None):
        self.rows["objects"].append({"object_type":kind,"object_id":obj.id,"version":obj.version,"visible":obj.visible,"timestamp":str(obj.timestamp),"changeset":obj.changeset,"uid":obj.uid,"user":obj.user,"longitude":lon,"latitude":lat})
        self.rows["tags"].extend({"object_type":kind,"object_id":obj.id,"version":obj.version,"key":tag.k,"value":tag.v} for tag in obj.tags)
        self.seen += 1
        if len(self.rows["objects"]) >= self.batch_rows: self.flush()
        if self.limit and self.seen >= self.limit: raise StopIteration

    def node(self, obj):
        lon = obj.location.lon if obj.location.valid() else None; lat = obj.location.lat if obj.location.valid() else None
        self.common(obj, "node", lon, lat)

    def way(self, obj):
        self.common(obj, "way")
        self.rows["way_nodes"].extend({"way_id":obj.id,"version":obj.version,"position":i,"node_id":node.ref} for i,node in enumerate(obj.nodes))

    def relation(self, obj):
        self.common(obj, "relation")
        self.rows["relation_members"].extend({"relation_id":obj.id,"version":obj.version,"position":i,"member_type":member.type,"member_id":member.ref,"role":member.role} for i,member in enumerate(obj.members))

    def flush(self):
        for name, rows in self.rows.items():
            if rows: self.writers[name].write_table(pa.Table.from_pylist(rows, schema=self.schemas[name])); rows.clear()

    def close(self):
        self.flush()
        for writer in self.writers.values(): writer.close()


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--config", default="configs/default.json"); parser.add_argument("--output-dir", default="data/processed"); parser.add_argument("--batch-rows", type=int, default=100_000); parser.add_argument("--limit", type=int); args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]; cfg = json.loads((root / args.config).read_text(encoding="utf-8")); source = root / "data/raw" / cfg["snapshot_date"] / cfg["filename"]
    handler = Handler(root / args.output_dir, args.batch_rows, args.limit)
    try: handler.apply_file(str(source), locations=False)
    except StopIteration: pass
    finally: handler.close()


if __name__ == "__main__": main()
