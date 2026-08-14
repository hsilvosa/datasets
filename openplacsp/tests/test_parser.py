from pathlib import Path

from openplacsp_pipeline.parser import iter_entries

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def test_parses_versions_relationships_and_deletion():
    with FIXTURE.open("rb") as handle:
        rows = list(iter_entries(handle, source_archive="fixture.zip", source_member="sample.atom"))
    assert len(rows) == 2
    first = rows[0]
    assert first.version["folder_id"] == "EXP-1"
    assert first.version["contracting_party_nif"] == "S1234567A"
    assert first.version["estimated_value"] == 150000
    assert first.lots[0]["lot_id"] == "1"
    assert [row["cpv_code"] for row in first.cpv_codes] == ["38000000", "38510000"]
    assert first.awards[0]["winner_nif"] == "B12345678"
    assert first.awards[0]["award_tax_exclusive"] == 59000
    assert rows[1].version["is_deleted"] is True
