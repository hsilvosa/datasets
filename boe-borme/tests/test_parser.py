from __future__ import annotations

from datetime import date

from conftest import fixture_path, load_fixture

from boe_borme.parser import (
    parse_aux,
    parse_legislacion_analisis,
    parse_legislacion_metadata,
    parse_sumario,
    parse_sumario_xml,
    parse_texto,
    xml_status_code,
)


def _by_id(rows, identifier):
    return next(row for row in rows if row["document_id"] == identifier)


def test_parse_boe_sumario_flattens_polymorphic_shapes():
    parsed = parse_sumario(load_fixture("sumario_boe.json"), "BOE")
    assert parsed["publication_date"] == date(2024, 1, 15)
    rows = parsed["documents"]
    assert len(rows) == 4
    first = _by_id(rows, "BOE-A-2024-1")
    assert first["publication"] == "BOE"
    assert first["issue_numero"] == "13"
    assert first["issue_id"] == "BOE-S-2024-13"
    assert first["seccion_codigo"] == "1"
    assert first["departamento_nombre"] == "MINISTERIO A"
    assert first["epigrafe_nombre"] == "Epigrafe Uno"
    assert first["pdf_pagina_inicial"] == 1
    assert first["pdf_pagina_final"] == 3

    second = _by_id(rows, "BOE-A-2024-2")
    assert second["departamento_nombre"] == "MINISTERIO B"
    assert second["epigrafe_nombre"] == "Epigrafe Dos"

    third = _by_id(rows, "BOE-B-2024-3")
    assert third["seccion_codigo"] == "3"
    assert third["departamento_nombre"] == "MINISTERIO C"
    assert third["epigrafe_nombre"] is None


def test_parse_borme_sumario_sections_and_apartados():
    parsed = parse_sumario(load_fixture("sumario_borme.json"), "BORME")
    rows = parsed["documents"]
    assert len(rows) == 3
    first = _by_id(rows, "BORME-C-2024-147")
    assert first["publication"] == "BORME"
    assert first["seccion_codigo"] == "A"
    assert first["apartado_codigo"] == "001"
    assert first["apartado_nombre"] == "BALANCES"
    second = _by_id(rows, "BORME-B-2024-1")
    assert second["seccion_codigo"] == "B"
    assert second["apartado_codigo"] is None


def test_parse_legislacion_metadata():
    row = parse_legislacion_metadata(load_fixture("legislacion_item.json"))
    assert row["identificador"] == "BOE-A-1978-31229"
    assert row["ambito_texto"] == "Estatal"
    assert row["departamento_codigo"] == "5140"
    assert row["fecha_disposicion"] == date(1978, 12, 27)
    assert row["fecha_vigencia"] == date(1978, 12, 29)
    assert row["estado_consolidacion_texto"] == "Finalizado"


def test_parse_legislacion_analisis():
    materias, references = parse_legislacion_analisis(load_fixture("analisis.json"), "BOE-A-1978-31229")
    assert [row["materia_codigo"] for row in materias] == ["1616", "1617"]
    assert {row["direction"] for row in references} == {"anteriores", "posteriores"}
    assert {row["relacion_texto"] for row in references} == {"DEROGA", "MODIFICA"}


def test_parse_texto_counts_blocks_and_text():
    xml = fixture_path("texto.xml").read_text(encoding="utf-8")
    row = parse_texto(xml, "BOE-A-1978-31229")
    assert row["id_norma"] == "BOE-A-1978-31229"
    assert row["block_count"] == 2
    assert row["char_count"] > 0
    assert "Estado social" in row["texto_plain"]


def test_parse_aux_dict_payload():
    rows = parse_aux({"2": "A Coruna", "3": "B"}, "materias")
    assert rows == [
        {"table": "materias", "codigo": "2", "texto": "A Coruna"},
        {"table": "materias", "codigo": "3", "texto": "B"},
    ]


def test_parse_sumario_xml_fallback_matches_json_shape():
    content = fixture_path("sumario_boe.xml").read_bytes()
    assert xml_status_code(content) == "200"
    parsed = parse_sumario_xml(content, "BOE")
    assert parsed["publication_date"] == date(1970, 1, 2)
    rows = parsed["documents"]
    assert len(rows) == 1
    row = rows[0]
    assert row["document_id"] == "BOE-A-1970-1"
    assert row["issue_id"] == "BOE-S-1970-2"
    assert row["issue_url_pdf"].endswith("BOE-S-1970-2.pdf")
    assert row["departamento_nombre"] == "MINISTERIO A"
    assert row["epigrafe_nombre"] == "Epigrafe Uno"
    assert row["url_pdf"].endswith("BOE-A-1970-1.pdf")
    assert row["pdf_pagina_inicial"] == 1
    assert row["pdf_pagina_final"] == 3
