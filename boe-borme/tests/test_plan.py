from __future__ import annotations

from conftest import write_raw_tree

from boe_borme import layout
from boe_borme.extract import build_plan


def base_config(make_config, **overrides):
    settings = {
        "boe_start_date": "2024-01-15",
        "borme_start_date": "2024-01-15",
        "end_date": "2024-01-17",
        "include_borme_sumario": False,
        "include_legislacion": False,
        "include_legislacion_texto": False,
        "include_aux": False,
        "refresh_days": 0,
    }
    settings.update(overrides)
    return make_config(**settings)


def test_plan_skips_completed_dates(make_config):
    config = base_config(make_config)
    layout.write_date_payload(config.raw_dir, layout.BOE_SUMARIO, "20240115", b"{}")
    plan = build_plan(config, [])
    assert [unit.unit for unit in plan[layout.BOE_SUMARIO]] == ["20240116", "20240117"]


def test_refresh_window_forces_recheck(make_config):
    config = base_config(make_config, refresh_days=7)
    layout.write_date_payload(config.raw_dir, layout.BOE_SUMARIO, "20240115", b"{}")
    plan = build_plan(config, [])
    assert [unit.unit for unit in plan[layout.BOE_SUMARIO]] == ["20240115", "20240116", "20240117"]


def test_norm_plan_includes_missing_and_excludes_complete(make_config):
    config = base_config(
        make_config,
        include_boe_sumario=False,
        include_legislacion=True,
        include_legislacion_texto=True,
    )
    item = {"identificador": "BOE-A-1", "fecha_actualizacion": "20260914T125535Z"}
    other = {"identificador": "BOE-A-2", "fecha_actualizacion": "20260914T125535Z"}
    plan = build_plan(config, [item, other])
    assert [unit.unit for unit in plan[layout.BOE_LEGISLACION]] == ["BOE-A-1", "BOE-A-2"]
    assert [unit.unit for unit in plan[layout.BOE_LEGISLACION_TEXTO]] == ["BOE-A-1", "BOE-A-2"]

    write_raw_tree(config, norm_ids=("BOE-A-1",), boe_dates=(), borme_dates=(), aux_names=())
    plan = build_plan(config, [item, other])
    assert [unit.unit for unit in plan[layout.BOE_LEGISLACION]] == ["BOE-A-2"]
    assert [unit.unit for unit in plan[layout.BOE_LEGISLACION_TEXTO]] == ["BOE-A-2"]
