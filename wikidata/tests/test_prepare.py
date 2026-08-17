import importlib.util
from pathlib import Path


path = Path(__file__).parents[1] / "scripts" / "prepare.py"
spec = importlib.util.spec_from_file_location("prepare", path)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def test_transform_emits_terms_and_claims():
    entity = {"id":"Q1","type":"item","lastrevid":3,"labels":{"en":{"value":"Universe"}},"claims":{"P1":[{"id":"Q1$1","rank":"normal","mainsnak":{"snaktype":"value"}}]}}
    tables = prepare.transform(entity)
    assert tables["entities"][0]["entity_id"] == "Q1"
    assert tables["terms"][0]["value"] == "Universe"
    assert tables["claims"][0]["property_id"] == "P1"
