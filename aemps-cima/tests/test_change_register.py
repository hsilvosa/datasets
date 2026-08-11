from pathlib import Path
from typing import Any

from aemps_cima.config import Config
from aemps_cima.extract import _change_checkpoint_path, _download_change_register
from aemps_cima.io_utils import read_jsonl, write_jsonl_atomic


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.rows = {
            "A": [{"id": 1, "nregistro": "A"}, {"id": 2, "nregistro": "A"}],
            "B": [{"id": 3, "nregistro": "B"}, {"id": 4, "nregistro": "B"}],
            "C": [{"id": 5, "nregistro": "C"}],
        }

    def paginated(self, endpoint: str, **params: Any):
        assert endpoint == "registroCambios"
        assert params["fecha"] == "01/01/2000"
        registration = str(params["nregistro"])
        self.calls.append(registration)
        yield from self.rows[registration]


def config_for(tmp_path: Path) -> Config:
    return Config(
        base_url="https://example.test",
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        artifacts_dir=tmp_path / "artifacts",
        staging_dir=tmp_path / "staging",
        request_delay_seconds=0,
        change_register_workers=2,
    )


def write_index(config: Config) -> None:
    write_jsonl_atomic(
        config.raw_dir / "medication_index.ndjson",
        ({"nregistro": item} for item in ("A", "B", "C")),
    )


def test_change_register_resumes_from_medication_checkpoints(tmp_path: Path) -> None:
    config = config_for(tmp_path)
    write_index(config)
    checkpoint_dir = config.raw_dir / "change_registers"
    write_jsonl_atomic(
        _change_checkpoint_path(checkpoint_dir, "B"),
        [{"id": 3, "nregistro": "B"}, {"id": 4, "nregistro": "B"}],
    )
    client = FakeClient()

    changes_path, count = _download_change_register(client, config)

    assert count == 5
    assert list(read_jsonl(changes_path)) == [
        {"id": 1, "nregistro": "A"},
        {"id": 2, "nregistro": "A"},
        {"id": 3, "nregistro": "B"},
        {"id": 4, "nregistro": "B"},
        {"id": 5, "nregistro": "C"},
    ]
    assert sorted(client.calls) == ["A", "C"]

    client.calls.clear()
    _download_change_register(client, config)
    assert client.calls == []


def test_change_register_refetches_mismatched_checkpoint(tmp_path: Path) -> None:
    config = config_for(tmp_path)
    write_index(config)
    checkpoint_dir = config.raw_dir / "change_registers"
    checkpoint_path = _change_checkpoint_path(checkpoint_dir, "B")
    write_jsonl_atomic(checkpoint_path, [{"id": 3, "nregistro": "WRONG"}])
    client = FakeClient()

    _download_change_register(client, config)

    assert sorted(client.calls) == ["A", "B", "C"]
    assert list(read_jsonl(checkpoint_path)) == [
        {"id": 3, "nregistro": "B"},
        {"id": 4, "nregistro": "B"},
    ]
