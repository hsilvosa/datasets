from __future__ import annotations

import bz2
import io
import json
import urllib.error
from pathlib import Path
from typing import Self

import pytest

from bne_linked_data import client
from bne_linked_data.client import DownloadError, download_one
from bne_linked_data.config import Config


class Response(io.BytesIO):
    status = 200

    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args) -> None:
        self.close()


def _config(tmp_path: Path) -> Config:
    project = tmp_path / "project"
    config_dir = project / "configs"
    config_dir.mkdir(parents=True)
    payload = {
        "snapshot_date": "2021-01-21",
        "raw_dir": "data/raw",
        "processed_dir": "data/processed",
        "artifacts_dir": "artifacts",
        "staging_dir": "hf_staging",
        "chunk_rows": 100,
        "timeout_seconds": 1,
        "retries": 1,
        "collections": [
            {
                "name": "subjects",
                "url": "https://example.org/materias.nt.bz2",
                "filename": "materias.nt.bz2",
                "expected_bytes": 36_300_000,
            }
        ],
    }
    path = config_dir / "test.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return Config.load(path)


def test_download_uses_server_length_not_rounded_estimate(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    payload = bz2.compress(b"small-real-response")
    monkeypatch.setattr(client, "_request", lambda *args: Response(payload))
    result = download_one(config, config.collections[0])
    assert result.bytes == len(payload)
    assert config.raw_path(config.collections[0]).read_bytes() == payload


def test_cloudflare_403_has_actionable_error(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)

    def forbidden(*args):
        raise urllib.error.HTTPError("https://example.org", 403, "Forbidden", {}, None)

    monkeypatch.setattr(client, "_request", forbidden)
    with pytest.raises(DownloadError, match="Cloudflare"):
        download_one(config, config.collections[0])


def test_existing_html_block_page_is_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    destination = config.raw_path(config.collections[0])
    destination.parent.mkdir(parents=True)
    destination.write_text("<html>blocked</html>", encoding="utf-8")
    with pytest.raises(DownloadError, match="not a BZip2"):
        download_one(config, config.collections[0])
