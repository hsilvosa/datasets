from __future__ import annotations

import html
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import Config
from .io_utils import read_jsonl

TABLE_NAMES = (
    "medications",
    "presentations",
    "active_ingredients",
    "excipients",
    "atc_codes",
    "administration_routes",
    "documents",
    "document_links",
    "photos",
    "changes",
    "master_data",
)


def _schemas() -> dict[str, Any]:
    """Return stable schemas without importing PyArrow when the module is imported."""
    import pyarrow as pa

    string = pa.string()
    integer = pa.int64()
    boolean = pa.bool_()

    def schema(fields: list[tuple[str, Any]]) -> Any:
        return pa.schema(fields)

    return {
        "medications": schema(
            [
                ("registration_number", string), ("name", string),
                ("holder_laboratory", string), ("marketing_laboratory", string),
                ("prescription_conditions", string), ("dose", string),
                ("marketed", boolean), ("prescription_required", boolean),
                ("generic", boolean), ("affects_driving", boolean),
                ("black_triangle", boolean), ("orphan_drug", boolean),
                ("biosimilar", boolean), ("ema_authorized", boolean),
                ("supply_problem", boolean), ("has_safety_notes", boolean),
                ("has_information_materials", boolean), ("authorized_at", integer),
                ("suspended_at", integer), ("withdrawn_at", integer),
                ("pharmaceutical_form_id", integer), ("pharmaceutical_form_code", string),
                ("pharmaceutical_form_name", string),
                ("simplified_pharmaceutical_form_id", integer),
                ("simplified_pharmaceutical_form_code", string),
                ("simplified_pharmaceutical_form_name", string),
                ("non_substitutable_id", integer), ("non_substitutable_code", string),
                ("non_substitutable_name", string),
                ("virtual_therapeutic_moiety_id", integer),
                ("virtual_therapeutic_moiety_code", string),
                ("virtual_therapeutic_moiety_name", string),
            ]
        ),
        "presentations": schema(
            [
                ("registration_number", string), ("national_code", string), ("name", string),
                ("marketed", boolean), ("supply_problem", boolean), ("position", integer),
                ("authorized_at", integer), ("suspended_at", integer),
                ("withdrawn_at", integer),
            ]
        ),
        "active_ingredients": schema(
            [
                ("registration_number", string), ("position", integer),
                ("ingredient_id", integer), ("ingredient_code", string),
                ("ingredient_name", string), ("quantity", string), ("unit", string),
            ]
        ),
        "excipients": schema(
            [
                ("registration_number", string), ("position", integer),
                ("excipient_id", integer), ("excipient_name", string),
                ("quantity", string), ("unit", string), ("source_order", integer),
            ]
        ),
        "atc_codes": schema(
            [
                ("registration_number", string), ("position", integer),
                ("atc_code", string), ("atc_name", string), ("atc_level", integer),
            ]
        ),
        "administration_routes": schema(
            [
                ("registration_number", string), ("position", integer),
                ("route_id", integer), ("route_code", string), ("route_name", string),
            ]
        ),
        "documents": schema(
            [
                ("registration_number", string), ("document_type", integer),
                ("section", string), ("title", string), ("source_order", integer),
                ("content_html", string), ("content_text", string),
            ]
        ),
        "document_links": schema(
            [
                ("registration_number", string), ("position", integer),
                ("document_type", integer), ("url", string), ("html_url", string),
                ("source_updated_at", integer), ("segmented_content_available", boolean),
            ]
        ),
        "photos": schema(
            [
                ("registration_number", string), ("position", integer),
                ("photo_type", string), ("url", string), ("source_updated_at", integer),
            ]
        ),
        "changes": schema(
            [
                ("registration_number", string), ("medication_name", string),
                ("holder_laboratory", string), ("changed_at", integer),
                ("change_type", integer), ("change_type_name", string),
                ("changed_field", string),
            ]
        ),
    }


class _ShardedWriter:
    """Bounded-memory Parquet writer that emits independent Hugging Face shards."""

    def __init__(self, output: Path, rows_per_file: int):
        self.output = output
        self.rows_per_file = rows_per_file
        self.schemas = _schemas()
        self.buffers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.parts: dict[str, int] = defaultdict(int)
        self.counts: dict[str, int] = defaultdict(int)

    def add(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        if not rows or table_name not in self.schemas:
            return
        buffer = self.buffers[table_name]
        buffer.extend(rows)
        while len(buffer) >= self.rows_per_file:
            self._write(table_name, buffer[: self.rows_per_file])
            del buffer[: self.rows_per_file]

    def _write(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        table_dir = self.output / table_name
        table_dir.mkdir(parents=True, exist_ok=True)
        part = self.parts[table_name]
        table = pa.Table.from_pylist(rows, schema=self.schemas[table_name])
        pq.write_table(
            table,
            table_dir / f"part-{part:05d}.parquet",
            compression="zstd",
            use_dictionary=True,
        )
        self.parts[table_name] += 1
        self.counts[table_name] += len(rows)

    def finish(self) -> dict[str, int]:
        for table_name, rows in self.buffers.items():
            if rows:
                self._write(table_name, rows)
        return {name: self.counts.get(name, 0) for name in TABLE_NAMES}


def _flatten_item(prefix: str, item: dict | None) -> dict[str, Any]:
    item = item or {}
    return {
        f"{prefix}_id": item.get("id"),
        f"{prefix}_code": item.get("codigo"),
        f"{prefix}_name": item.get("nombre"),
    }


def _flatten_state(state: dict | None) -> dict[str, Any]:
    state = state or {}
    return {
        "authorized_at": state.get("aut"),
        "suspended_at": state.get("susp"),
        "withdrawn_at": state.get("rev"),
    }


def strip_html(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def normalize_medication(record: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    registration = str(record.get("nregistro", ""))
    medication = {
        "registration_number": registration,
        "name": record.get("nombre"),
        "holder_laboratory": record.get("labtitular"),
        "marketing_laboratory": record.get("labcomercializador"),
        "prescription_conditions": record.get("cpresc"),
        "dose": record.get("dosis"),
        "marketed": record.get("comerc"),
        "prescription_required": record.get("receta"),
        "generic": record.get("generico"),
        "affects_driving": record.get("conduc"),
        "black_triangle": record.get("triangulo"),
        "orphan_drug": record.get("huerfano"),
        "biosimilar": record.get("biosimilar"),
        "ema_authorized": record.get("ema"),
        "supply_problem": record.get("psum"),
        "has_safety_notes": record.get("notas"),
        "has_information_materials": record.get("materialesInf"),
        **_flatten_state(record.get("estado")),
        **_flatten_item("pharmaceutical_form", record.get("formaFarmaceutica")),
        **_flatten_item(
            "simplified_pharmaceutical_form", record.get("formaFarmaceuticaSimplificada")
        ),
        **_flatten_item("non_substitutable", record.get("nosustituible")),
        **_flatten_item("virtual_therapeutic_moiety", record.get("vtm")),
    }
    tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tables["medications"].append(medication)
    for position, row in enumerate(record.get("presentaciones") or []):
        tables["presentations"].append(
            {
                "registration_number": registration,
                "national_code": row.get("cn"),
                "name": row.get("nombre"),
                "marketed": row.get("comerc"),
                "supply_problem": row.get("psum"),
                "position": position,
                **_flatten_state(row.get("estado")),
            }
        )
    for position, row in enumerate(record.get("principiosActivos") or []):
        tables["active_ingredients"].append(
            {
                "registration_number": registration,
                "position": position,
                "ingredient_id": row.get("id"),
                "ingredient_code": row.get("codigo"),
                "ingredient_name": row.get("nombre"),
                "quantity": row.get("cantidad"),
                "unit": row.get("unidad"),
            }
        )
    for position, row in enumerate(record.get("excipientes") or []):
        tables["excipients"].append(
            {
                "registration_number": registration,
                "position": position,
                "excipient_id": row.get("id"),
                "excipient_name": row.get("nombre"),
                "quantity": row.get("cantidad"),
                "unit": row.get("unidad"),
                "source_order": row.get("orden"),
            }
        )
    for position, row in enumerate(record.get("atcs") or []):
        tables["atc_codes"].append(
            {
                "registration_number": registration,
                "position": position,
                "atc_code": row.get("codigo"),
                "atc_name": row.get("nombre"),
                "atc_level": row.get("nivel"),
            }
        )
    for position, row in enumerate(record.get("viasAdministracion") or []):
        tables["administration_routes"].append(
            {
                "registration_number": registration,
                "position": position,
                "route_id": row.get("id"),
                "route_code": row.get("codigo"),
                "route_name": row.get("nombre"),
            }
        )
    for position, row in enumerate(record.get("docs") or []):
        tables["document_links"].append(
            {
                "registration_number": registration,
                "position": position,
                "document_type": row.get("tipo"),
                "url": row.get("url"),
                "html_url": row.get("urlHtml"),
                "source_updated_at": row.get("fecha"),
                "segmented_content_available": row.get("secc"),
            }
        )
    for position, row in enumerate(record.get("fotos") or []):
        tables["photos"].append(
            {
                "registration_number": registration,
                "position": position,
                "photo_type": row.get("tipo"),
                "url": row.get("url"),
                "source_updated_at": row.get("fecha"),
            }
        )
    return dict(tables)


def normalize(config: Config) -> dict[str, int]:
    if config.processed_dir.exists():
        shutil.rmtree(config.processed_dir)
    config.processed_dir.mkdir(parents=True)
    writer = _ShardedWriter(config.processed_dir, config.parquet_rows_per_file)

    for medication in read_jsonl(config.raw_dir / "medications.ndjson"):
        for name, rows in normalize_medication(medication).items():
            writer.add(name, rows)

    for response in read_jsonl(config.raw_dir / "documents.ndjson"):
        sections = response.get("sections") or []
        if isinstance(sections, dict):
            sections = sections.get("resultados") or sections.get("secciones") or []
        for position, section in enumerate(sections):
            content = section.get("contenido")
            writer.add(
                "documents",
                [{
                    "registration_number": str(response.get("nregistro", "")),
                    "document_type": response.get("document_type"),
                    "section": section.get("seccion"),
                    "title": section.get("titulo"),
                    "source_order": section.get("orden", position),
                    "content_html": content,
                    "content_text": strip_html(content),
                }],
            )

    for event in read_jsonl(config.raw_dir / "changes.ndjson"):
        changed_fields = event.get("cambios") or event.get("cambio") or [None]
        change_type = event.get("tipoCambio")
        for changed_field in changed_fields:
            writer.add(
                "changes",
                [{
                    "registration_number": str(event.get("nregistro", "")),
                    "medication_name": event.get("nombre"),
                    "holder_laboratory": event.get("labtitular"),
                    "changed_at": event.get("fecha"),
                    "change_type": change_type,
                    "change_type_name": {1: "new", 2: "withdrawn", 3: "modified"}.get(
                        change_type, "unknown"
                    ),
                    "changed_field": changed_field,
                }],
            )
    return writer.finish()
