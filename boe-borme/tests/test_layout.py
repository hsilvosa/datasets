from __future__ import annotations

from boe_borme import layout


def test_date_roundtrip_and_completion(make_config):
    config = make_config()
    date8 = "20240115"
    assert not layout.is_date_complete(config.raw_dir, layout.BOE_SUMARIO, date8)
    path = layout.write_date_payload(config.raw_dir, layout.BOE_SUMARIO, date8, b'{"a": 1}')
    assert path.exists()
    assert layout.is_date_complete(config.raw_dir, layout.BOE_SUMARIO, date8)


def test_empty_marker_marks_complete(make_config):
    config = make_config()
    date8 = "20240114"
    layout.mark_date_empty(config.raw_dir, layout.BOE_SUMARIO, date8, "http-404", "now")
    assert layout.is_date_complete(config.raw_dir, layout.BOE_SUMARIO, date8)
    payloads, empties = layout.count_date_files(config.raw_dir, layout.BOE_SUMARIO)
    assert (payloads, empties) == (0, 1)


def test_norm_completion_flags(make_config):
    config = make_config()
    norm_id = "BOE-A-1"
    assert not layout.is_metadata_complete(config.raw_dir, norm_id)
    layout.write_norm_metadata(config.raw_dir, norm_id, {"identificador": norm_id})
    assert layout.is_metadata_complete(config.raw_dir, norm_id)
    assert not layout.is_analisis_complete(config.raw_dir, norm_id)
    assert not layout.is_texto_complete(config.raw_dir, norm_id)
