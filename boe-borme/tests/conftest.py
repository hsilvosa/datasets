from __future__ import annotations

import json
from pathlib import Path

import pytest

from boe_borme import layout
from boe_borme.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_path(name: str) -> Path:
    return FIXTURES / name


def load_fixture(name: str):
    return json.loads(fixture_path(name).read_text(encoding="utf-8"))


def copy_fixture(name: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(fixture_path(name).read_bytes())
    return target


DEFAULT_NORM = "BOE-A-1978-31229"


def write_raw_tree(
    config,
    *,
    boe_dates=("20240115",),
    borme_dates=("20240115",),
    norm_ids=(DEFAULT_NORM,),
    aux_names=None,
    catalog=True,
) -> None:
    raw = config.raw_dir
    for date8 in boe_dates:
        copy_fixture("sumario_boe.json", raw / "boe_sumario" / date8[:4] / f"{date8}.json")
    for date8 in borme_dates:
        copy_fixture("sumario_borme.json", raw / "borme_sumario" / date8[:4] / f"{date8}.json")
    for norm_id in norm_ids:
        copy_fixture("legislacion_item.json", raw / "boe_legislacion" / norm_id / "metadata.json")
        copy_fixture("analisis.json", raw / "boe_legislacion" / norm_id / "analisis.json")
        copy_fixture("texto.xml", raw / "boe_legislacion_texto" / norm_id / "texto.xml")
    names = list(aux_names) if aux_names is not None else list(layout.AUX_TABLES)
    for name in names:
        copy_fixture("aux_materias.json", raw / "boe_aux" / f"{name}.json")
    if catalog:
        catalog_dir = raw / "boe_legislacion"
        catalog_dir.mkdir(parents=True, exist_ok=True)
        items = []
        for norm_id in norm_ids:
            item = load_fixture("legislacion_item.json")
            item["identificador"] = norm_id
            items.append(item)
        (catalog_dir / "_catalog.json").write_text(
            json.dumps({"items": items}), encoding="utf-8"
        )


@pytest.fixture
def make_config(tmp_path):
    def factory(**overrides) -> Config:
        base = {
            "raw_dir": tmp_path / "raw",
            "processed_dir": tmp_path / "processed",
            "artifacts_dir": tmp_path / "artifacts",
            "state_dir": tmp_path / "state",
            "staging_dir": tmp_path / "staging",
        }
        base.update(overrides)
        config = Config(**base)
        config.validate()
        return config

    return factory
