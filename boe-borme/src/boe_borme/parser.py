from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

CHILD_KEYS = ("departamento", "epigrafe", "apartado", "texto", "grupo", "seccion", "item")
_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"<bloque\b")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, dict):
        for key in ("texto", "#text", "text"):
            if key in value:
                return text_value(value[key])
        return None
    stripped = str(value).strip()
    return stripped or None


def int_value(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def compact_date(value: Any) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _url(value: Any) -> str | None:
    if isinstance(value, dict):
        return text_value(value.get("texto")) or text_value(value)
    return text_value(value)


def _enrich(key: str, node: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    updated = dict(context)
    if key == "seccion":
        updated["seccion_codigo"] = text_value(node.get("codigo"))
        updated["seccion_nombre"] = text_value(node.get("nombre"))
    elif key == "departamento":
        updated["departamento_codigo"] = text_value(node.get("codigo"))
        updated["departamento_nombre"] = text_value(node.get("nombre"))
    elif key == "epigrafe":
        updated["epigrafe_nombre"] = text_value(node.get("nombre")) or text_value(
            node.get("texto")
        )
    elif key == "apartado":
        updated["apartado_codigo"] = text_value(node.get("codigo"))
        updated["apartado_nombre"] = text_value(node.get("nombre"))
    return updated


def _item_row(node: dict[str, Any], context: dict[str, Any], publication: str) -> dict[str, Any]:
    url_pdf = node.get("url_pdf")
    pdf = url_pdf if isinstance(url_pdf, dict) else {}
    row = {
        "publication": publication,
        "publication_date": context.get("publication_date"),
        "issue_numero": context.get("issue_numero"),
        "issue_id": context.get("issue_id"),
        "issue_url_pdf": context.get("issue_url_pdf"),
        "seccion_codigo": context.get("seccion_codigo"),
        "seccion_nombre": context.get("seccion_nombre"),
        "departamento_codigo": context.get("departamento_codigo"),
        "departamento_nombre": context.get("departamento_nombre"),
        "epigrafe_nombre": context.get("epigrafe_nombre"),
        "apartado_codigo": context.get("apartado_codigo"),
        "apartado_nombre": context.get("apartado_nombre"),
        "document_id": text_value(node.get("identificador")),
        "control": text_value(node.get("control")),
        "titulo": text_value(node.get("titulo")),
        "url_html": text_value(node.get("url_html")),
        "url_xml": text_value(node.get("url_xml")),
        "url_pdf": _url(url_pdf),
        "pdf_pagina_inicial": int_value(pdf.get("pagina_inicial")),
        "pdf_pagina_final": int_value(pdf.get("pagina_final")),
        "pdf_szbytes": int_value(pdf.get("szBytes")),
        "pdf_szkbytes": int_value(pdf.get("szKBytes")),
    }
    return row


def _is_item(node: dict[str, Any]) -> bool:
    return "identificador" in node and "titulo" in node


def _walk_children(node: dict[str, Any], context: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    for key in CHILD_KEYS:
        if key not in node:
            continue
        for child in as_list(node[key]):
            if not isinstance(child, dict):
                continue
            if _is_item(child):
                rows.append(_item_row(child, context, context["publication"]))
                continue
            _walk_children(child, _enrich(key, child, context), rows)


def parse_sumario(payload: dict[str, Any], publication: str) -> dict[str, Any]:
    data = payload.get("data") or {}
    sumario = data.get("sumario") or {}
    metadata = sumario.get("metadatos") or {}
    publication_date = compact_date(metadata.get("fecha_publicacion"))
    documents: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for diario in as_list(sumario.get("diario")):
        if not isinstance(diario, dict):
            continue
        sumario_diario = diario.get("sumario_diario") or {}
        issue = {
            "publication": publication,
            "publication_date": publication_date,
            "issue_numero": text_value(diario.get("numero")),
            "issue_id": text_value(sumario_diario.get("identificador")),
            "issue_url_pdf": _url(sumario_diario.get("url_pdf")),
        }
        issues.append(issue)
        for seccion in as_list(diario.get("seccion")):
            if not isinstance(seccion, dict):
                continue
            context = {
                **issue,
                "publication": publication,
                "seccion_codigo": text_value(seccion.get("codigo")),
                "seccion_nombre": text_value(seccion.get("nombre")),
            }
            _walk_children(seccion, context, documents)
    return {"publication_date": publication_date, "issues": issues, "documents": documents}


def xml_to_dict(element: ET.Element) -> Any:
    """Convert a BOE XML response into the same shape as the JSON response."""
    result: dict[str, Any] = dict(element.attrib)
    children = list(element)
    if not children:
        text = (element.text or "").strip()
        if result:
            if text:
                result["#text"] = text
            return result
        return text or None
    for child in children:
        key = child.tag
        value = xml_to_dict(child)
        if key in result:
            existing = result[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                result[key] = [existing, value]
        else:
            result[key] = value
    text = (element.text or "").strip()
    if text and "#text" not in result:
        result["#text"] = text
    return result


def xml_payload(content: bytes) -> dict[str, Any]:
    payload = xml_to_dict(ET.fromstring(content))
    return payload if isinstance(payload, dict) else {}


def xml_status_code(content: bytes) -> str:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return ""
    code = root.find("./status/code")
    return (code.text or "").strip() if code is not None else ""


def parse_sumario_xml(content: bytes, publication: str) -> dict[str, Any]:
    return parse_sumario(xml_payload(content), publication)


def parse_legislacion_metadata(item: dict[str, Any]) -> dict[str, Any]:
    def pair(key: str) -> tuple[str | None, str | None]:
        value = item.get(key)
        if isinstance(value, dict):
            return text_value(value.get("codigo")), text_value(value.get("texto"))
        return None, text_value(value)

    ambito_codigo, ambito_texto = pair("ambito")
    departamento_codigo, departamento_texto = pair("departamento")
    rango_codigo, rango_texto = pair("rango")
    estado_codigo, estado_texto = pair("estado_consolidacion")
    return {
        "identificador": text_value(item.get("identificador")),
        "fecha_actualizacion": text_value(item.get("fecha_actualizacion")),
        "titulo": text_value(item.get("titulo")),
        "ambito_codigo": ambito_codigo,
        "ambito_texto": ambito_texto,
        "departamento_codigo": departamento_codigo,
        "departamento_texto": departamento_texto,
        "rango_codigo": rango_codigo,
        "rango_texto": rango_texto,
        "fecha_disposicion": compact_date(item.get("fecha_disposicion")),
        "fecha_publicacion": compact_date(item.get("fecha_publicacion")),
        "fecha_vigencia": compact_date(item.get("fecha_vigencia")),
        "diario": text_value(item.get("diario")),
        "diario_numero": text_value(item.get("diario_numero")),
        "numero_oficial": text_value(item.get("numero_oficial")),
        "vigencia_agotada": text_value(item.get("vigencia_agotada")),
        "estado_consolidacion_codigo": estado_codigo,
        "estado_consolidacion_texto": estado_texto,
        "url_eli": text_value(item.get("url_eli")),
        "url_html_consolidada": text_value(item.get("url_html_consolidada")),
    }


def _materia_nodes(value: Any) -> list[Any]:
    if isinstance(value, dict):
        if "materia" in value:
            return as_list(value["materia"])
        return [value]
    return as_list(value)


def _relations(value: Any) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    for group in as_list(value):
        if isinstance(group, dict):
            for nested in group.values():
                for relation in as_list(nested):
                    if isinstance(relation, dict):
                        relations.append(relation)
        elif isinstance(group, list):
            for relation in group:
                if isinstance(relation, dict):
                    relations.append(relation)
    return relations


def _iter_references(value: Any):
    if isinstance(value, dict):
        for direction, groups in value.items():
            for relation in _relations(groups):
                yield direction, relation
    elif isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict):
                for direction, groups in entry.items():
                    for relation in _relations(groups):
                        yield direction, relation


def parse_legislacion_analisis(
    payload: dict[str, Any], norm_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = as_list(payload.get("data"))
    node = data[0] if data and isinstance(data[0], dict) else {}
    materias: list[dict[str, Any]] = []
    for materia in _materia_nodes(node.get("materias")):
        if isinstance(materia, dict):
            materias.append(
                {
                    "id_norma": norm_id,
                    "materia_codigo": text_value(materia.get("codigo")),
                    "materia_texto": text_value(materia.get("texto")),
                }
            )
    references: list[dict[str, Any]] = []
    for direction, relation in _iter_references(node.get("referencias")):
        relacion = relation.get("relacion") or {}
        references.append(
            {
                "id_norma": norm_id,
                "direction": text_value(direction),
                "related_id": text_value(relation.get("id_norma")),
                "relacion_codigo": text_value(relacion.get("codigo")) if isinstance(relacion, dict) else None,
                "relacion_texto": text_value(relacion.get("texto")) if isinstance(relacion, dict) else None,
                "texto": text_value(relation.get("texto")),
            }
        )
    return materias, references


def xml_to_text(xml_text: str) -> str:
    without_blocks = xml_text.replace("<br/>", "\n").replace("<br />", "\n").replace("</p>", "\n")
    stripped = _TAG.sub(" ", without_blocks)
    unescaped = html.unescape(stripped)
    lines = [" ".join(line.split()) for line in unescaped.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_texto(xml_text: str, norm_id: str) -> dict[str, Any]:
    plain = xml_to_text(xml_text)
    return {
        "id_norma": norm_id,
        "texto_xml": xml_text,
        "texto_plain": plain,
        "char_count": len(plain),
        "block_count": len(_BLOCK.findall(xml_text)),
    }


def parse_aux(data: Any, table: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for code, value in data.items():
            if isinstance(value, dict):
                rows.append(
                    {
                        "table": table,
                        "codigo": str(code),
                        "texto": text_value(value.get("texto")) or text_value(value.get("nombre")),
                    }
                )
            else:
                rows.append({"table": table, "codigo": str(code), "texto": text_value(value)})
    elif isinstance(data, list):
        for value in data:
            if isinstance(value, dict):
                rows.append(
                    {
                        "table": table,
                        "codigo": text_value(value.get("codigo")),
                        "texto": text_value(value.get("texto")) or text_value(value.get("nombre")),
                    }
                )
    return rows
