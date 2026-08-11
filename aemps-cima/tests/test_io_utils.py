import json

from aemps_cima.io_utils import repair_jsonl


def test_repair_jsonl_removes_malformed_and_duplicate_rows(tmp_path) -> None:
    path = tmp_path / "records.ndjson"
    path.write_text(
        '{"id":"a","value":1}\nnot-json\n{"id":"a","value":2}\n{"id":"b","value":3}\n',
        encoding="utf-8",
    )
    result = repair_jsonl(path, "id")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert result == {"valid": 2, "duplicates": 1, "malformed": 1}
    assert rows == [{"id": "a", "value": 1}, {"id": "b", "value": 3}]
