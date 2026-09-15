from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from . import layout
from .config import Config
from .io_utils import append_jsonl, atomic_json, read_jsonl, sha256, stable_hash
from .parser import (
    parse_aux,
    parse_legislacion_analisis,
    parse_legislacion_metadata,
    parse_sumario,
    parse_texto,
)

TABLE_BOE_SUMARIO = "boe_sumario"
TABLE_BORME_SUMARIO = "borme_sumario"
TABLE_LEGISLACION = "boe_legislacion"
TABLE_MATERIAS = "boe_legislacion_materias"
TABLE_REFERENCIAS = "boe_legislacion_referencias"
TABLE_TEXTO = "boe_legislacion_texto"
TABLE_AUX = "boe_aux"

ALL_TABLES = (
    TABLE_BOE_SUMARIO,
    TABLE_BORME_SUMARIO,
    TABLE_LEGISLACION,
    TABLE_MATERIAS,
    TABLE_REFERENCIAS,
    TABLE_TEXTO,
    TABLE_AUX,
)


def _common_fields() -> list[tuple[str, pa.DataType]]:
    return [
        ("source_sha256", pa.string()),
        ("retrieved_at_utc", pa.timestamp("s", tz="UTC")),
        ("run_id", pa.string()),
    ]


SUMARIO_SCHEMA = pa.schema(
    [
        ("publication", pa.string()),
        ("publication_date", pa.date32()),
        ("issue_numero", pa.string()),
        ("issue_id", pa.string()),
        ("issue_url_pdf", pa.string()),
        ("seccion_codigo", pa.string()),
        ("seccion_nombre", pa.string()),
        ("departamento_codigo", pa.string()),
        ("departamento_nombre", pa.string()),
        ("epigrafe_nombre", pa.string()),
        ("apartado_codigo", pa.string()),
        ("apartado_nombre", pa.string()),
        ("document_id", pa.string()),
        ("control", pa.string()),
        ("titulo", pa.string()),
        ("url_html", pa.string()),
        ("url_xml", pa.string()),
        ("url_pdf", pa.string()),
        ("pdf_pagina_inicial", pa.int32()),
        ("pdf_pagina_final", pa.int32()),
        ("pdf_szbytes", pa.int64()),
        ("pdf_szkbytes", pa.int32()),
        *_common_fields(),
    ]
)

LEGISLACION_SCHEMA = pa.schema(
    [
        ("identificador", pa.string()),
        ("fecha_actualizacion", pa.string()),
        ("titulo", pa.string()),
        ("ambito_codigo", pa.string()),
        ("ambito_texto", pa.string()),
        ("departamento_codigo", pa.string()),
        ("departamento_texto", pa.string()),
        ("rango_codigo", pa.string()),
        ("rango_texto", pa.string()),
        ("fecha_disposicion", pa.date32()),
        ("fecha_publicacion", pa.date32()),
        ("fecha_vigencia", pa.date32()),
        ("diario", pa.string()),
        ("diario_numero", pa.string()),
        ("numero_oficial", pa.string()),
        ("vigencia_agotada", pa.string()),
        ("estado_consolidacion_codigo", pa.string()),
        ("estado_consolidacion_texto", pa.string()),
        ("url_eli", pa.string()),
        ("url_html_consolidada", pa.string()),
        *_common_fields(),
    ]
)

MATERIAS_SCHEMA = pa.schema(
    [
        ("id_norma", pa.string()),
        ("materia_codigo", pa.string()),
        ("materia_texto", pa.string()),
        *_common_fields(),
    ]
)

REFERENCIAS_SCHEMA = pa.schema(
    [
        ("id_norma", pa.string()),
        ("direction", pa.string()),
        ("related_id", pa.string()),
        ("relacion_codigo", pa.string()),
        ("relacion_texto", pa.string()),
        ("texto", pa.string()),
        *_common_fields(),
    ]
)

TEXTO_SCHEMA = pa.schema(
    [
        ("id_norma", pa.string()),
        ("texto_xml", pa.string()),
        ("texto_plain", pa.string()),
        ("char_count", pa.int64()),
        ("block_count", pa.int32()),
        *_common_fields(),
    ]
)

AUX_SCHEMA = pa.schema(
    [
        ("table", pa.string()),
        ("codigo", pa.string()),
        ("texto", pa.string()),
        *_common_fields(),
    ]
)

SCHEMAS = {
    TABLE_BOE_SUMARIO: SUMARIO_SCHEMA,
    TABLE_BORME_SUMARIO: SUMARIO_SCHEMA,
    TABLE_LEGISLACION: LEGISLACION_SCHEMA,
    TABLE_MATERIAS: MATERIAS_SCHEMA,
    TABLE_REFERENCIAS: REFERENCIAS_SCHEMA,
    TABLE_TEXTO: TEXTO_SCHEMA,
    TABLE_AUX: AUX_SCHEMA,
}

SOURCE_TABLES = {
    "boe_sumario": (TABLE_BOE_SUMARIO,),
    "borme_sumario": (TABLE_BORME_SUMARIO,),
    "boe_legislacion_metadata": (TABLE_LEGISLACION,),
    "boe_legislacion_analisis": (TABLE_MATERIAS, TABLE_REFERENCIAS),
    "boe_legislacion_texto": (TABLE_TEXTO,),
    "boe_aux": (TABLE_AUX,),
}


@dataclass(frozen=True)
class RawObject:
    source: str
    key: str
    path: Path


def _mtime_utc(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _common(path: Path, run_id: str) -> dict:
    return {
        "source_sha256": sha256(path),
        "retrieved_at_utc": _mtime_utc(path),
        "run_id": run_id,
    }


def _load_date(path: Path, run_id: str, publication: str) -> dict[str, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    parsed = parse_sumario(payload, publication)
    common = _common(path, run_id)
    rows = [{**document, **common} for document in parsed["documents"]]
    table = TABLE_BOE_SUMARIO if publication == "BOE" else TABLE_BORME_SUMARIO
    return {table: rows}


def _load_metadata(path: Path, run_id: str) -> dict[str, list[dict]]:
    item = json.loads(path.read_text(encoding="utf-8"))
    return {TABLE_LEGISLACION: [{**parse_legislacion_metadata(item), **_common(path, run_id)}]}


def _load_analisis(path: Path, run_id: str) -> dict[str, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    norm_id = path.parent.name
    materias, references = parse_legislacion_analisis(payload, norm_id)
    common = _common(path, run_id)
    return {
        TABLE_MATERIAS: [{**row, **common} for row in materias],
        TABLE_REFERENCIAS: [{**row, **common} for row in references],
    }


def _load_texto(path: Path, run_id: str) -> dict[str, list[dict]]:
    text = path.read_text(encoding="utf-8")
    row = parse_texto(text, path.parent.name)
    return {TABLE_TEXTO: [{**row, **_common(path, run_id)}]}


def _load_aux(path: Path, run_id: str) -> dict[str, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    table = path.stem
    rows = parse_aux(payload.get("data"), table)
    common = _common(path, run_id)
    return {TABLE_AUX: [{**row, **common} for row in rows]}


LOADERS: dict[str, Callable[[Path, str], dict[str, list[dict]]]] = {
    "boe_sumario": lambda path, run_id: _load_date(path, run_id, "BOE"),
    "borme_sumario": lambda path, run_id: _load_date(path, run_id, "BORME"),
    "boe_legislacion_metadata": _load_metadata,
    "boe_legislacion_analisis": _load_analisis,
    "boe_legislacion_texto": _load_texto,
    "boe_aux": _load_aux,
}


def enumerate_objects(config: Config) -> list[RawObject]:
    objects: list[RawObject] = []
    if config.include_boe_sumario:
        for path in (config.raw_dir / layout.BOE_SUMARIO).glob("*/*.json"):
            if not path.name.endswith(".empty.json"):
                objects.append(
                    RawObject("boe_sumario", f"boe_sumario|{path.stem}|{sha256(path)}", path)
                )
    if config.include_borme_sumario:
        for path in (config.raw_dir / layout.BORME_SUMARIO).glob("*/*.json"):
            if not path.name.endswith(".empty.json"):
                objects.append(
                    RawObject("borme_sumario", f"borme_sumario|{path.stem}|{sha256(path)}", path)
                )
    if config.include_legislacion:
        for norm_id, path in layout.iter_norm_metadata(config.raw_dir):
            objects.append(
                RawObject(
                    "boe_legislacion_metadata",
                    f"boe_legislacion_metadata|{norm_id}|{sha256(path)}",
                    path,
                )
            )
        for norm_id, path in layout.iter_norm_analisis(config.raw_dir):
            objects.append(
                RawObject(
                    "boe_legislacion_analisis",
                    f"boe_legislacion_analisis|{norm_id}|{sha256(path)}",
                    path,
                )
            )
    if config.include_legislacion and config.include_legislacion_texto:
        for norm_id, path in layout.iter_norm_texto(config.raw_dir):
            objects.append(
                RawObject(
                    "boe_legislacion_texto",
                    f"boe_legislacion_texto|{norm_id}|{sha256(path)}",
                    path,
                )
            )
    if config.include_aux:
        for name, path in layout.iter_aux(config.raw_dir):
            objects.append(RawObject("boe_aux", f"boe_aux|{name}|{sha256(path)}", path))
    return objects


def _write_table(path: Path, rows: list[dict], schema: pa.Schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(table, temporary, compression="zstd")
    temporary.replace(path)


def _batch_paths(config: Config, source: str, batch: str) -> list[Path]:
    return [
        config.processed_dir / table / f"part-{source}-{batch}.parquet"
        for table in SOURCE_TABLES[source]
    ]


def run_normalize(config: Config) -> dict:
    batches_path = config.state_dir / "batches.jsonl"
    verified_objects: set[str] = set()
    for record in read_jsonl(batches_path):
        paths = _batch_paths(config, record["source"], record["batch"])
        if all(path.exists() for path in paths):
            verified_objects.update(record["objects"])
    objects = enumerate_objects(config)
    pending = [obj for obj in objects if obj.key not in verified_objects]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    by_source: dict[str, list[RawObject]] = defaultdict(list)
    for obj in pending:
        by_source[obj.source].append(obj)

    totals: dict[str, int] = defaultdict(int)
    files_written = 0
    for source, items in by_source.items():
        items.sort(key=lambda obj: obj.key)
        loader = LOADERS[source]
        for index in range(0, len(items), config.shard_objects):
            chunk = items[index : index + config.shard_objects]
            batch = stable_hash([obj.key for obj in chunk])
            paths = _batch_paths(config, source, batch)
            if all(path.exists() for path in paths):
                append_jsonl(
                    batches_path,
                    {"source": source, "batch": batch, "objects": [obj.key for obj in chunk]},
                )
                continue
            rows_by_table: dict[str, list[dict]] = {table: [] for table in SOURCE_TABLES[source]}
            for obj in chunk:
                for table, rows in loader(obj.path, run_id).items():
                    rows_by_table[table].extend(rows)
            for table in SOURCE_TABLES[source]:
                table_path = config.processed_dir / table / f"part-{source}-{batch}.parquet"
                _write_table(table_path, rows_by_table[table], SCHEMAS[table])
                totals[table] += len(rows_by_table[table])
                files_written += 1
            append_jsonl(
                batches_path,
                {"source": source, "batch": batch, "objects": [obj.key for obj in chunk]},
            )
    summary = {
        "run_id": run_id,
        "objects_total": len(objects),
        "objects_pending": len(pending),
        "objects_verified": len(verified_objects),
        "objects_normalized": len(objects) - len(verified_objects),
        "files_written": files_written,
        "table_rows": dict(totals),
    }
    atomic_json(config.state_dir / "last_normalize.json", summary)
    return summary
