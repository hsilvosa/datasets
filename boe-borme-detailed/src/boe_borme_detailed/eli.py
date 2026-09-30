from __future__ import annotations

from typing import Any


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def decompose_eli(url: str | None) -> dict[str, Any]:
    empty = {
        "eli_pais": None,
        "eli_tipo": None,
        "eli_anio": None,
        "eli_mes": None,
        "eli_dia": None,
        "eli_ordinal": None,
    }
    if not url or "/eli/" not in url:
        return empty
    rest = url.split("/eli/", 1)[1].strip("/")
    parts = [part for part in rest.split("/") if part]
    ordinal = None
    if parts and parts[-1].startswith("("):
        ordinal = parts[-1].strip("()")
        parts = parts[:-1]
    return {
        "eli_pais": parts[0] if len(parts) > 0 else None,
        "eli_tipo": parts[1] if len(parts) > 1 else None,
        "eli_anio": _int(parts[2]) if len(parts) > 2 else None,
        "eli_mes": _int(parts[3]) if len(parts) > 3 else None,
        "eli_dia": _int(parts[4]) if len(parts) > 4 else None,
        "eli_ordinal": ordinal,
    }
