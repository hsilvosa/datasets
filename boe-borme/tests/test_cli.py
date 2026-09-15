from __future__ import annotations

import json

from boe_borme.cli import main


def write_config(tmp_path, **overrides):
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "raw_dir": "data/raw",
        "processed_dir": "data/processed",
        "artifacts_dir": "artifacts",
        "state_dir": "state",
        "staging_dir": "hf_staging",
        "include_borme_sumario": False,
        "include_legislacion": False,
        "include_legislacion_texto": False,
        "include_aux": False,
    }
    payload.update(overrides)
    path = config_dir / "default.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_status_command_runs(tmp_path, capsys):
    path = write_config(tmp_path)
    assert main(["status", "--config", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["coverage"]["boe_sumario"]["covered_days"] == 0


def test_status_reports_completed_dates(tmp_path, capsys):
    path = write_config(tmp_path)
    raw = tmp_path / "data" / "raw" / "boe_sumario" / "2024"
    raw.mkdir(parents=True)
    (raw / "20240115.json").write_text("{}", encoding="utf-8")
    assert main(["status", "--config", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["coverage"]["boe_sumario"]["payload_days"] == 1
