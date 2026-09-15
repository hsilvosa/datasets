from __future__ import annotations

from conftest import write_raw_tree

from boe_borme.analyze import run_analyze
from boe_borme.io_utils import read_json
from boe_borme.normalize import run_normalize


def analyze_quality(config):
    run_normalize(config)
    run_analyze(config)
    return read_json(config.artifacts_dir / "quality.json")


def test_analyze_passes_when_coverage_complete(make_config):
    config = make_config(
        boe_start_date="2024-01-15",
        borme_start_date="2024-01-15",
        end_date="2024-01-15",
    )
    write_raw_tree(config)
    quality = analyze_quality(config)
    assert quality["status"] == "pass"
    assert quality["gaps"] == []
    assert quality["coverage"]["boe_sumario"]["gap_days"] == 0
    assert quality["coverage"]["boe_legislacion"]["texto_norms"] == 1


def test_analyze_fails_on_date_gap(make_config):
    config = make_config(
        boe_start_date="2024-01-15",
        borme_start_date="2024-01-15",
        end_date="2024-01-16",
    )
    write_raw_tree(config)
    quality = analyze_quality(config)
    assert quality["status"] == "fail"
    assert any("boe_sumario gap_days=1" in gap for gap in quality["gaps"])


def test_analyze_fails_on_missing_aux(make_config):
    config = make_config(
        boe_start_date="2024-01-15",
        borme_start_date="2024-01-15",
        end_date="2024-01-15",
    )
    write_raw_tree(config, aux_names=("materias",))
    quality = analyze_quality(config)
    assert quality["status"] == "fail"
    assert any("boe_aux missing" in gap for gap in quality["gaps"])
