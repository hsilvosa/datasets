import importlib.util
from pathlib import Path


path = Path(__file__).parents[1] / "scripts" / "prepare.py"
spec = importlib.util.spec_from_file_location("prepare", path)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def test_parse_dly_skips_missing_values():
    header = "TEST0000001" + "2024" + "02" + "TMAX"
    fields = "  123   " + "-9999   " + "  456 Q " + "-9999   " * 26
    rows = list(prepare.parse_dly(header + fields))
    assert [row["value"] for row in rows] == [123, 456]
    assert rows[1]["quality_flag"] == "Q"
