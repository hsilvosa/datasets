from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from .io_utils import atomic_bytes, atomic_json, read_json

BOE_SUMARIO = "boe_sumario"
BORME_SUMARIO = "borme_sumario"
BOE_LEGISLACION = "boe_legislacion"
BOE_LEGISLACION_TEXTO = "boe_legislacion_texto"
BOE_AUX = "boe_aux"

AUX_TABLES = (
    "materias",
    "ambitos",
    "estados-consolidacion",
    "departamentos",
    "rangos",
    "relaciones-anteriores",
    "relaciones-posteriores",
)

CATALOG_PATH = "_catalog.json"


# --- date based sources (BOE / BORME sumarios) -------------------------------


def date_dir(raw_dir: Path, dataset: str, date8: str) -> Path:
    return raw_dir / dataset / date8[:4]


def date_path(raw_dir: Path, dataset: str, date8: str) -> Path:
    return date_dir(raw_dir, dataset, date8) / f"{date8}.json"


def date_empty_marker(raw_dir: Path, dataset: str, date8: str) -> Path:
    return date_dir(raw_dir, dataset, date8) / f"{date8}.empty.json"


def is_date_complete(raw_dir: Path, dataset: str, date8: str) -> bool:
    return date_path(raw_dir, dataset, date8).exists() or date_empty_marker(
        raw_dir, dataset, date8
    ).exists()


def write_date_payload(raw_dir: Path, dataset: str, date8: str, content: bytes) -> Path:
    path = date_path(raw_dir, dataset, date8)
    atomic_bytes(path, content)
    return path


def mark_date_empty(raw_dir: Path, dataset: str, date8: str, reason: str, retrieved_at: str) -> None:
    atomic_json(
        date_empty_marker(raw_dir, dataset, date8),
        {"date": date8, "retrieved_at_utc": retrieved_at, "reason": reason},
    )


def iter_date_files(raw_dir: Path, dataset: str) -> Iterator[Path]:
    root = raw_dir / dataset
    if not root.exists():
        return
    yield from sorted(root.glob("*/*.json"))
    yield from sorted(root.glob("*/*.empty.json"))


def count_date_files(raw_dir: Path, dataset: str) -> tuple[int, int]:
    payloads = 0
    empties = 0
    root = raw_dir / dataset
    if root.exists():
        for path in root.glob("*/*.json"):
            if path.name.endswith(".empty.json"):
                empties += 1
            else:
                payloads += 1
    return payloads, empties


# --- consolidated legislation ------------------------------------------------


def norm_dir(raw_dir: Path, dataset: str, norm_id: str) -> Path:
    return raw_dir / dataset / norm_id


def norm_metadata_path(raw_dir: Path, norm_id: str) -> Path:
    return norm_dir(raw_dir, BOE_LEGISLACION, norm_id) / "metadata.json"


def norm_analisis_path(raw_dir: Path, norm_id: str) -> Path:
    return norm_dir(raw_dir, BOE_LEGISLACION, norm_id) / "analisis.json"


def norm_analisis_empty(raw_dir: Path, norm_id: str) -> Path:
    return norm_dir(raw_dir, BOE_LEGISLACION, norm_id) / "analisis.empty.json"


def norm_texto_path(raw_dir: Path, norm_id: str) -> Path:
    return norm_dir(raw_dir, BOE_LEGISLACION_TEXTO, norm_id) / "texto.xml"


def norm_texto_empty(raw_dir: Path, norm_id: str) -> Path:
    return norm_dir(raw_dir, BOE_LEGISLACION_TEXTO, norm_id) / "texto.empty.json"


def write_norm_metadata(raw_dir: Path, norm_id: str, item: dict) -> Path:
    path = norm_metadata_path(raw_dir, norm_id)
    atomic_bytes(path, (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8"))
    return path


def is_metadata_complete(raw_dir: Path, norm_id: str) -> bool:
    path = norm_metadata_path(raw_dir, norm_id)
    return path.exists() and path.stat().st_size > 0


def is_analisis_complete(raw_dir: Path, norm_id: str) -> bool:
    return norm_analisis_path(raw_dir, norm_id).exists() or norm_analisis_empty(
        raw_dir, norm_id
    ).exists()


def is_texto_complete(raw_dir: Path, norm_id: str) -> bool:
    return norm_texto_path(raw_dir, norm_id).exists() or norm_texto_empty(
        raw_dir, norm_id
    ).exists()


def iter_norm_metadata(raw_dir: Path) -> Iterator[tuple[str, Path]]:
    root = raw_dir / BOE_LEGISLACION
    if not root.exists():
        return
    for directory in sorted(root.iterdir()):
        if directory.is_dir():
            path = directory / "metadata.json"
            if path.exists():
                yield directory.name, path


def iter_norm_analisis(raw_dir: Path) -> Iterator[tuple[str, Path]]:
    root = raw_dir / BOE_LEGISLACION
    if not root.exists():
        return
    for directory in sorted(root.iterdir()):
        if directory.is_dir():
            path = directory / "analisis.json"
            if path.exists():
                yield directory.name, path


def iter_norm_texto(raw_dir: Path) -> Iterator[tuple[str, Path]]:
    root = raw_dir / BOE_LEGISLACION_TEXTO
    if not root.exists():
        return
    for directory in sorted(root.iterdir()):
        if directory.is_dir():
            path = directory / "texto.xml"
            if path.exists():
                yield directory.name, path


# --- auxiliary tables --------------------------------------------------------


def aux_path(raw_dir: Path, name: str) -> Path:
    return raw_dir / BOE_AUX / f"{name}.json"


def aux_empty_marker(raw_dir: Path, name: str) -> Path:
    return raw_dir / BOE_AUX / f"{name}.empty.json"


def is_aux_complete(raw_dir: Path, name: str) -> bool:
    return aux_path(raw_dir, name).exists() or aux_empty_marker(raw_dir, name).exists()


def iter_aux(raw_dir: Path) -> Iterator[tuple[str, Path]]:
    root = raw_dir / BOE_AUX
    if not root.exists():
        return
    for path in sorted(root.glob("*.json")):
        if path.name.endswith(".empty.json"):
            continue
        yield path.stem, path


# --- legislation catalog -----------------------------------------------------


def catalog_path(raw_dir: Path) -> Path:
    return raw_dir / BOE_LEGISLACION / CATALOG_PATH


def read_catalog(raw_dir: Path) -> list[dict]:
    path = catalog_path(raw_dir)
    if not path.exists():
        return []
    payload = read_json(path)
    return payload.get("items", [])
