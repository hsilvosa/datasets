from __future__ import annotations

import json

import pytest

from boe_borme.publish import stage


def test_stage_refuses_when_quality_fails(make_config):
    config = make_config(
        boe_start_date="2024-01-15",
        borme_start_date="2024-01-15",
        end_date="2024-01-15",
    )
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (config.artifacts_dir / "quality.json").write_text(
        json.dumps({"status": "fail", "gaps": ["boe_sumario gap_days=1"]}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="quality status is not pass"):
        stage(config)
