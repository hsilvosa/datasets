from aemps_cima.normalize import normalize_medication, strip_html


def test_normalize_medication_builds_relational_tables() -> None:
    source = {
        "nregistro": "12345",
        "nombre": "Example medicine",
        "estado": {"aut": 1000},
        "principiosActivos": [
            {"id": 7, "codigo": "ING-7", "nombre": "Example ingredient", "cantidad": "5"}
        ],
        "excipientes": [{"id": 8, "nombre": "Example excipient", "cantidad": "2"}],
        "atcs": [{"codigo": "A01AA", "nombre": "Example ATC", "nivel": 5}],
        "viasAdministracion": [{"id": 2, "codigo": "OR", "nombre": "Oral"}],
        "presentaciones": [{"cn": "999999", "nombre": "Box", "comerc": True}],
        "docs": [{"tipo": 1, "url": "https://example.test/document", "secc": True}],
        "fotos": [{"tipo": "package", "url": "https://example.test/photo"}],
    }
    tables = normalize_medication(source)
    assert tables["medications"][0]["registration_number"] == "12345"
    assert tables["active_ingredients"][0]["ingredient_id"] == 7
    assert tables["excipients"][0]["excipient_id"] == 8
    assert tables["presentations"][0]["national_code"] == "999999"
    assert tables["document_links"][0]["document_type"] == 1
    assert tables["photos"][0]["photo_type"] == "package"


def test_strip_html_preserves_readable_text() -> None:
    assert strip_html("<p>Dose&nbsp;<strong>once</strong> daily.</p>") == "Dose once daily."
