from __future__ import annotations

from datetime import date

from conftest import load_text

from boe_borme_detailed.blocks import parse_bloques


def test_parse_bloques_and_versions():
    bloques, versiones = parse_bloques(load_text("complex_texto.xml"), "BOE-A-2000-1")
    assert len(bloques) == 2
    assert len(versiones) == 3

    first = next(row for row in bloques if row["bloque_id"] == "a1")
    assert first["bloque_tipo"] == "precepto"
    assert first["bloque_titulo"] == "Articulo 1"
    assert first["version_count"] == 2
    assert first["version_id_norma"] == "BOE-A-2010-1"
    assert first["texto"] == "Segunda version del articulo uno."
    assert first["char_count"] == len(first["texto"])

    a1_versions = [row for row in versiones if row["bloque_id"] == "a1"]
    assert [row["version_index"] for row in a1_versions] == [0, 1]
    assert a1_versions[0]["version_id_norma"] == "BOE-A-2000-1"
    assert a1_versions[0]["fecha_hasta"] == date(2010, 1, 2)
    assert a1_versions[1]["fecha_hasta"] is None
    assert a1_versions[1]["fecha_vigencia"] == date(2010, 1, 2)

    second = next(row for row in bloques if row["bloque_id"] == "a2")
    assert second["fecha_caducidad"] == date(2020, 1, 1)
    assert second["version_count"] == 1
