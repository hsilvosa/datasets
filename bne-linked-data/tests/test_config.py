import json
from pathlib import Path

import pytest

from bne_linked_data.config import Config


def test_reject_duplicate_collection_names(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    item = {
        "name": "authorities",
        "url": "https://example.org/a.bz2",
        "filename": "a.bz2",
        "expected_bytes": 1,
    }
    payload = {
        "snapshot_date": "2021-01-21",
        "raw_dir": "data/raw",
        "processed_dir": "data/processed",
        "artifacts_dir": "artifacts",
        "staging_dir": "hf_staging",
        "chunk_rows": 100,
        "collections": [item, item],
    }
    path = config_dir / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        Config.load(path)

