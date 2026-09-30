from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

_WHITESPACE = re.compile(r"\s+")


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


def _clean(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _version_text(version: ET.Element) -> str:
    paragraphs = []
    for child in version:
        text = _clean(" ".join(child.itertext()))
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def parse_bloques(xml_text: str, identificador: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = ET.fromstring(xml_text)
    texto = root.find(".//texto")
    if texto is None:
        return [], []
    bloques: list[dict[str, Any]] = []
    versiones: list[dict[str, Any]] = []
    for orden, bloque in enumerate(texto.findall("bloque")):
        bloque_id = bloque.get("id")
        bloque_tipo = bloque.get("tipo")
        bloque_titulo = bloque.get("titulo")
        fecha_caducidad = compact_date(bloque.get("fecha_caducidad"))
        versions = bloque.findall("version")
        parsed: list[dict[str, Any]] = []
        for version in versions:
            fecha_publicacion = compact_date(version.get("fecha_publicacion"))
            fecha_vigencia = compact_date(version.get("fecha_vigencia"))
            text = _version_text(version)
            parsed.append(
                {
                    "identificador": identificador,
                    "bloque_id": bloque_id,
                    "bloque_tipo": bloque_tipo,
                    "bloque_titulo": bloque_titulo,
                    "orden": orden,
                    "version_id_norma": version.get("id_norma"),
                    "fecha_publicacion": fecha_publicacion,
                    "fecha_vigencia": fecha_vigencia,
                    "fecha_caducidad": fecha_caducidad,
                    "texto": text,
                    "char_count": len(text),
                }
            )
        for index, row in enumerate(parsed):
            following = parsed[index + 1]["fecha_vigencia"] if index + 1 < len(parsed) else None
            versiones.append({**row, "version_index": index, "fecha_hasta": following})
        if parsed:
            current = parsed[-1]
            bloques.append(
                {
                    "identificador": identificador,
                    "bloque_id": bloque_id,
                    "bloque_tipo": bloque_tipo,
                    "bloque_titulo": bloque_titulo,
                    "orden": orden,
                    "version_count": len(parsed),
                    "version_id_norma": current["version_id_norma"],
                    "fecha_publicacion": current["fecha_publicacion"],
                    "fecha_vigencia": current["fecha_vigencia"],
                    "fecha_caducidad": fecha_caducidad,
                    "texto": current["texto"],
                    "char_count": current["char_count"],
                }
            )
    return bloques, versiones
