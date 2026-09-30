from __future__ import annotations

import json

import pytest

from boe_borme_detailed.publish import card_body, stage


def test_card_body_strips_self_reference():
    body = card_body(
        "# Title\n\nIntro.\n\nPublished dataset: [x on Hugging Face](https://example.com)\n\nMore.\n"
    )
    assert "Published dataset:" not in body
    assert "# Title" in body
    assert "More." in body


def test_stage_refuses_when_quality_fails(make_config):
    config = make_config()
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (config.artifacts_dir / "quality.json").write_text(
        json.dumps({"status": "fail", "gaps": ["legislacion_bloques is empty"]}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="quality status is not pass"):
        stage(config)
