import importlib.util
from pathlib import Path


path = Path(__file__).parents[1] / "scripts" / "prepare.py"
spec = importlib.util.spec_from_file_location("prepare", path)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def test_transform_preserves_source_and_nutrition():
    row = prepare.transform({"code": "1", "product_name": "Tea", "nutriments": {"energy-kcal_100g": 0}})
    assert row["code"] == "1"
    assert '"energy-kcal_100g":0' in row["nutriments_json"]
    assert '"product_name":"Tea"' in row["source_json"]
