import json
from unittest.mock import patch

from aemps_cima.client import CimaClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_paginated_reads_all_reported_pages() -> None:
    payloads = [
        {"resultados": [{"id": 1}], "totalFilas": 2, "tamanioPagina": 1},
        {"resultados": [{"id": 2}], "totalFilas": 2, "tamanioPagina": 1},
    ]
    with patch("urllib.request.urlopen", side_effect=[FakeResponse(item) for item in payloads]):
        client = CimaClient("https://example.test", delay=0)
        assert list(client.paginated("items")) == [{"id": 1}, {"id": 2}]


def test_paginated_preserves_filters_on_every_page() -> None:
    payloads = [
        {"resultados": [{"id": 1}], "totalFilas": 2, "tamanioPagina": 1},
        {"resultados": [{"id": 2}], "totalFilas": 2, "tamanioPagina": 1},
    ]
    with patch(
        "urllib.request.urlopen", side_effect=[FakeResponse(item) for item in payloads]
    ) as call:
        client = CimaClient("https://example.test", delay=0)
        list(client.paginated("changes", fecha="01/08/2026"))
        requested_urls = [entry.args[0].full_url for entry in call.call_args_list]
        assert all("fecha=01%2F08%2F2026" in url for url in requested_urls)
        assert requested_urls[1].endswith("pagina=2&fecha=01%2F08%2F2026")
