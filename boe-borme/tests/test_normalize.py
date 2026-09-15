from __future__ import annotations

from pathlib import Path

import pyarrow.dataset as ds
from conftest import write_raw_tree

from boe_borme.io_utils import sha256
from boe_borme.normalize import run_normalize


def snapshot(directory: Path) -> dict[str, str]:
    return {str(path.relative_to(directory)): sha256(path) for path in directory.rglob("*.parquet")}


def table_rows(directory: Path) -> int:
    if not directory.exists():
        return 0
    return ds.dataset(directory, format="parquet").count_rows()


def test_normalize_is_append_only_and_idempotent(make_config):
    config = make_config(
        boe_start_date="2024-01-15",
        borme_start_date="2024-01-15",
        end_date="2024-01-15",
    )
    write_raw_tree(config)
    summary = run_normalize(config)
    assert summary["objects_pending"] > 0
    assert summary["table_rows"]["boe_sumario"] == 4
    assert summary["table_rows"]["borme_sumario"] == 3
    assert summary["table_rows"]["boe_legislacion"] == 1
    assert summary["table_rows"]["boe_legislacion_materias"] == 2
    assert summary["table_rows"]["boe_legislacion_referencias"] == 2
    assert summary["table_rows"]["boe_legislacion_texto"] == 1
    assert summary["table_rows"]["boe_aux"] == 3 * 7

    before = snapshot(config.processed_dir)
    second = run_normalize(config)
    assert second["objects_pending"] == 0
    assert second["files_written"] == 0
    assert snapshot(config.processed_dir) == before

    write_raw_tree(config, boe_dates=("20240115", "20240116"), borme_dates=("20240115",))
    third = run_normalize(config)
    after = snapshot(config.processed_dir)
    assert third["files_written"] > 0
    for path, digest in before.items():
        assert after[path] == digest
    assert len(after) > len(before)
    assert table_rows(config.processed_dir / "boe_sumario") == 8
