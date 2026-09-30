from __future__ import annotations

from pathlib import Path

from conftest import write_base_tables

from boe_borme_detailed.analyze import run_analyze
from boe_borme_detailed.derive import run_derive
from boe_borme_detailed.io_utils import read_json, sha256


def snapshot(directory: Path) -> dict[str, str]:
    return {str(path.relative_to(directory)): sha256(path) for path in directory.rglob("*.parquet")}


def test_derive_is_append_only_and_idempotent(make_config):
    config = make_config()
    write_base_tables(config)
    first = run_derive(config)
    assert first["table_rows"]["legislacion_bloques"] == 2
    assert first["table_rows"]["legislacion_versiones"] == 3
    assert first["table_rows"]["legislacion_eli"] == 1
    assert first["table_rows"]["documento_legislacion"] == 1

    before = snapshot(config.processed_dir)
    second = run_derive(config)
    assert second["files_written"] == 0
    assert snapshot(config.processed_dir) == before

    write_base_tables(
        config,
        texts=(
            ("BOE-A-2000-1", "complex_texto.xml", "sha-text-1"),
            ("BOE-A-2001-1", "complex_texto.xml", "sha-text-2"),
        ),
        legislacion=(
            ("BOE-A-2000-1", "sha-leg-1", "https://www.boe.es/eli/es/l/2000/01/01/1"),
            ("BOE-A-2001-1", "sha-leg-2", "https://www.boe.es/eli/es/l/2001/01/01/1"),
        ),
        sumario=(("BOE-A-2000-1", "sha-suma-1"), ("BOE-A-2001-1", "sha-suma-2")),
    )
    third = run_derive(config)
    after = snapshot(config.processed_dir)
    assert third["files_written"] > 0
    for path, digest in before.items():
        assert after[path] == digest
    assert len(after) > len(before)


def test_analyze_passes_after_derive(make_config):
    config = make_config()
    write_base_tables(config)
    run_derive(config)
    profile = run_analyze(config)
    assert profile["total_rows"] > 0
    quality = read_json(config.artifacts_dir / "quality.json")
    assert quality["status"] == "pass"
    assert quality["gaps"] == []
    assert quality["coverage"]["documento_unmatched_norms"] == 0
