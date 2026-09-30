from __future__ import annotations

from boe_borme_detailed.eli import decompose_eli


def test_decompose_standard_eli():
    result = decompose_eli("https://www.boe.es/eli/es/c/1978/12/27/(1)")
    assert result == {
        "eli_pais": "es",
        "eli_tipo": "c",
        "eli_anio": 1978,
        "eli_mes": 12,
        "eli_dia": 27,
        "eli_ordinal": "1",
    }


def test_decompose_regional_eli():
    result = decompose_eli("https://www.boe.es/eli/es-an/l/2007/10/22/1")
    assert result["eli_pais"] == "es-an"
    assert result["eli_tipo"] == "l"
    assert result["eli_anio"] == 2007


def test_decompose_missing_returns_nulls():
    assert decompose_eli(None)["eli_pais"] is None
    assert decompose_eli("https://example.com/x")["eli_anio"] is None
