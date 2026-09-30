from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from .blocks import parse_bloques
from .config import Config
from .eli import decompose_eli
from .io_utils import append_jsonl, atomic_json, read_jsonl, stable_hash

TABLE_BLOQUES = "legislacion_bloques"
TABLE_VERSIONES = "legislacion_versiones"
TABLE_ELI = "legislacion_eli"
TABLE_DOCUMENTO = "documento_legislacion"

ALL_TABLES = (TABLE_BLOQUES, TABLE_VERSIONES, TABLE_ELI, TABLE_DOCUMENTO)

GROUP_TABLES = {
    "texto": (TABLE_BLOQUES, TABLE_VERSIONES),
    "legislacion": (TABLE_ELI,),
    "documento": (TABLE_DOCUMENTO,),
}

BASE_TEXTO = "boe_legislacion_texto"
BASE_LEGISLACION = "boe_legislacion"
BASE_SUMARIO = "boe_sumario"


def _common_fields() -> list[tuple[str, pa.DataType]]:
    return [
        ("source_sha256", pa.string()),
        ("retrieved_at_utc", pa.timestamp("s", tz="UTC")),
        ("run_id", pa.string()),
    ]


BLOQUES_SCHEMA = pa.schema(
    [
        ("identificador", pa.string()),
        ("bloque_id", pa.string()),
        ("bloque_tipo", pa.string()),
        ("bloque_titulo", pa.string()),
        ("orden", pa.int32()),
        ("version_count", pa.int32()),
        ("version_id_norma", pa.string()),
        ("fecha_publicacion", pa.date32()),
        ("fecha_vigencia", pa.date32()),
        ("fecha_caducidad", pa.date32()),
        ("texto", pa.string()),
        ("char_count", pa.int64()),
        *_common_fields(),
    ]
)

VERSIONES_SCHEMA = pa.schema(
    [
        ("identificador", pa.string()),
        ("bloque_id", pa.string()),
        ("bloque_tipo", pa.string()),
        ("bloque_titulo", pa.string()),
        ("orden", pa.int32()),
        ("version_index", pa.int32()),
        ("version_id_norma", pa.string()),
        ("fecha_publicacion", pa.date32()),
        ("fecha_vigencia", pa.date32()),
        ("fecha_hasta", pa.date32()),
        ("fecha_caducidad", pa.date32()),
        ("texto", pa.string()),
        ("char_count", pa.int64()),
        *_common_fields(),
    ]
)

ELI_SCHEMA = pa.schema(
    [
        ("identificador", pa.string()),
        ("titulo", pa.string()),
        ("url_eli", pa.string()),
        ("url_html_consolidada", pa.string()),
        ("eli_pais", pa.string()),
        ("eli_tipo", pa.string()),
        ("eli_anio", pa.int32()),
        ("eli_mes", pa.int32()),
        ("eli_dia", pa.int32()),
        ("eli_ordinal", pa.string()),
        ("rango_codigo", pa.string()),
        ("rango_texto", pa.string()),
        ("departamento_codigo", pa.string()),
        ("departamento_texto", pa.string()),
        ("ambito_codigo", pa.string()),
        ("ambito_texto", pa.string()),
        ("estado_consolidacion_codigo", pa.string()),
        ("estado_consolidacion_texto", pa.string()),
        ("vigencia_agotada", pa.string()),
        ("fecha_publicacion", pa.date32()),
        ("fecha_disposicion", pa.date32()),
        ("fecha_vigencia", pa.date32()),
        *_common_fields(),
    ]
)

DOCUMENTO_SCHEMA = pa.schema(
    [
        ("identificador", pa.string()),
        ("document_id", pa.string()),
        ("publication", pa.string()),
        ("publication_date", pa.date32()),
        ("issue_id", pa.string()),
        ("issue_numero", pa.string()),
        ("seccion_codigo", pa.string()),
        ("seccion_nombre", pa.string()),
        ("departamento_codigo", pa.string()),
        ("departamento_nombre", pa.string()),
        ("epigrafe_nombre", pa.string()),
        ("titulo", pa.string()),
        ("url_html", pa.string()),
        ("url_xml", pa.string()),
        ("url_pdf", pa.string()),
        *_common_fields(),
    ]
)

SCHEMAS = {
    TABLE_BLOQUES: BLOQUES_SCHEMA,
    TABLE_VERSIONES: VERSIONES_SCHEMA,
    TABLE_ELI: ELI_SCHEMA,
    TABLE_DOCUMENTO: DOCUMENTO_SCHEMA,
}


@dataclass(frozen=True)
class DerivedObject:
    group: str
    key: str
    identifier: str
    sha: str


def _dataset(config: Config, table: str) -> ds.Dataset:
    return ds.dataset(config.base_table_dir(table), format="parquet")


def _common(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_sha256": row.get("source_sha256"),
        "retrieved_at_utc": row.get("retrieved_at_utc"),
        "run_id": row.get("run_id"),
    }


def _load_texto(config: Config, identifiers: list[str], run_id: str) -> dict[str, list[dict]]:
    rows = _dataset(config, BASE_TEXTO).to_table(
        filter=ds.field("id_norma").isin(identifiers),
        columns=["id_norma", "texto_xml", "source_sha256", "retrieved_at_utc", "run_id"],
    ).to_pylist()
    bloques: list[dict] = []
    versiones: list[dict] = []
    for row in rows:
        block_rows, version_rows = parse_bloques(row["texto_xml"], row["id_norma"])
        common = _common(row)
        bloques.extend({**item, **common} for item in block_rows)
        versiones.extend({**item, **common} for item in version_rows)
    return {TABLE_BLOQUES: bloques, TABLE_VERSIONES: versiones}


def _load_legislacion(config: Config, identifiers: list[str], run_id: str) -> dict[str, list[dict]]:
    columns = [
        "identificador",
        "titulo",
        "url_eli",
        "url_html_consolidada",
        "rango_codigo",
        "rango_texto",
        "departamento_codigo",
        "departamento_texto",
        "ambito_codigo",
        "ambito_texto",
        "estado_consolidacion_codigo",
        "estado_consolidacion_texto",
        "vigencia_agotada",
        "fecha_publicacion",
        "fecha_disposicion",
        "fecha_vigencia",
        "source_sha256",
        "retrieved_at_utc",
        "run_id",
    ]
    rows = _dataset(config, BASE_LEGISLACION).to_table(
        filter=ds.field("identificador").isin(identifiers), columns=columns
    ).to_pylist()
    output: list[dict] = []
    for row in rows:
        decomposed = decompose_eli(row.get("url_eli"))
        output.append(
            {
                "identificador": row["identificador"],
                "titulo": row.get("titulo"),
                "url_eli": row.get("url_eli"),
                "url_html_consolidada": row.get("url_html_consolidada"),
                **decomposed,
                "rango_codigo": row.get("rango_codigo"),
                "rango_texto": row.get("rango_texto"),
                "departamento_codigo": row.get("departamento_codigo"),
                "departamento_texto": row.get("departamento_texto"),
                "ambito_codigo": row.get("ambito_codigo"),
                "ambito_texto": row.get("ambito_texto"),
                "estado_consolidacion_codigo": row.get("estado_consolidacion_codigo"),
                "estado_consolidacion_texto": row.get("estado_consolidacion_texto"),
                "vigencia_agotada": row.get("vigencia_agotada"),
                "fecha_publicacion": row.get("fecha_publicacion"),
                "fecha_disposicion": row.get("fecha_disposicion"),
                "fecha_vigencia": row.get("fecha_vigencia"),
                **_common(row),
            }
        )
    return {TABLE_ELI: output}


def _load_documento(config: Config, identifiers: list[str], run_id: str) -> dict[str, list[dict]]:
    columns = [
        "document_id",
        "publication",
        "publication_date",
        "issue_id",
        "issue_numero",
        "seccion_codigo",
        "seccion_nombre",
        "departamento_codigo",
        "departamento_nombre",
        "epigrafe_nombre",
        "titulo",
        "url_html",
        "url_xml",
        "url_pdf",
        "source_sha256",
        "retrieved_at_utc",
        "run_id",
    ]
    rows = _dataset(config, BASE_SUMARIO).to_table(
        filter=ds.field("document_id").isin(identifiers), columns=columns
    ).to_pylist()
    output: list[dict] = []
    for row in rows:
        output.append(
            {
                "identificador": row["document_id"],
                "document_id": row["document_id"],
                "publication": row.get("publication"),
                "publication_date": row.get("publication_date"),
                "issue_id": row.get("issue_id"),
                "issue_numero": row.get("issue_numero"),
                "seccion_codigo": row.get("seccion_codigo"),
                "seccion_nombre": row.get("seccion_nombre"),
                "departamento_codigo": row.get("departamento_codigo"),
                "departamento_nombre": row.get("departamento_nombre"),
                "epigrafe_nombre": row.get("epigrafe_nombre"),
                "titulo": row.get("titulo"),
                "url_html": row.get("url_html"),
                "url_xml": row.get("url_xml"),
                "url_pdf": row.get("url_pdf"),
                **_common(row),
            }
        )
    return {TABLE_DOCUMENTO: output}


LOADERS = {
    "texto": _load_texto,
    "legislacion": _load_legislacion,
    "documento": _load_documento,
}


def _norm_identifiers(config: Config) -> list[str]:
    table = _dataset(config, BASE_LEGISLACION).to_table(columns=["identificador"])
    return sorted({value for value in table.column("identificador").to_pylist() if value})


def enumerate_objects(config: Config) -> dict[str, list[DerivedObject]]:
    objects: dict[str, list[DerivedObject]] = defaultdict(list)

    texto = _dataset(config, BASE_TEXTO).to_table(columns=["id_norma", "source_sha256"])
    for identifier, sha in zip(
        texto.column("id_norma").to_pylist(), texto.column("source_sha256").to_pylist()
    ):
        if identifier and sha:
            objects["texto"].append(
                DerivedObject("texto", f"texto|{identifier}|{sha}", identifier, sha)
            )

    legislacion = _dataset(config, BASE_LEGISLACION).to_table(
        columns=["identificador", "source_sha256"]
    )
    norm_ids = set()
    for identifier, sha in zip(
        legislacion.column("identificador").to_pylist(),
        legislacion.column("source_sha256").to_pylist(),
    ):
        if identifier and sha:
            objects["legislacion"].append(
                DerivedObject("legislacion", f"legislacion|{identifier}|{sha}", identifier, sha)
            )
            norm_ids.add(identifier)

    sumario = _dataset(config, BASE_SUMARIO).to_table(columns=["document_id", "source_sha256"])
    for identifier, sha in zip(
        sumario.column("document_id").to_pylist(), sumario.column("source_sha256").to_pylist()
    ):
        if identifier in norm_ids and sha:
            objects["documento"].append(
                DerivedObject("documento", f"documento|{identifier}|{sha}", identifier, sha)
            )
    return objects


def _batch_paths(config: Config, group: str, batch: str) -> list[Path]:
    return [
        config.processed_dir / table / f"part-{group}-{batch}.parquet"
        for table in GROUP_TABLES[group]
    ]


def _write_table(path: Path, rows: list[dict], schema: pa.Schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(table, temporary, compression="zstd")
    temporary.replace(path)


def run_derive(config: Config) -> dict:
    batches_path = config.state_dir / "batches.jsonl"
    verified: set[str] = set()
    for record in read_jsonl(batches_path):
        paths = _batch_paths(config, record["group"], record["batch"])
        if all(path.exists() for path in paths):
            verified.update(record["objects"])

    objects = enumerate_objects(config)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    totals: dict[str, int] = defaultdict(int)
    files_written = 0
    pending_total = 0
    for group, items in objects.items():
        items.sort(key=lambda obj: obj.key)
        pending = [obj for obj in items if obj.key not in verified]
        pending_total += len(pending)
        for index in range(0, len(pending), config.shard_objects):
            chunk = pending[index : index + config.shard_objects]
            batch = stable_hash([obj.key for obj in chunk])
            paths = _batch_paths(config, group, batch)
            if all(path.exists() for path in paths):
                append_jsonl(
                    batches_path,
                    {"group": group, "batch": batch, "objects": [obj.key for obj in chunk]},
                )
                continue
            identifiers = [obj.identifier for obj in chunk]
            rows_by_table = LOADERS[group](config, identifiers, run_id)
            for table in GROUP_TABLES[group]:
                table_path = config.processed_dir / table / f"part-{group}-{batch}.parquet"
                _write_table(table_path, rows_by_table.get(table, []), SCHEMAS[table])
                totals[table] += len(rows_by_table.get(table, []))
                files_written += 1
            append_jsonl(
                batches_path,
                {"group": group, "batch": batch, "objects": [obj.key for obj in chunk]},
            )
    summary = {
        "run_id": run_id,
        "objects_total": sum(len(items) for items in objects.values()),
        "objects_pending": pending_total,
        "files_written": files_written,
        "table_rows": dict(totals),
    }
    atomic_json(config.state_dir / "last_derive.json", summary)
    return summary
