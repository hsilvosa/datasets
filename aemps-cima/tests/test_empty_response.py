from unittest.mock import patch

from aemps_cima.client import CimaClient


class EmptyResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return b""


def test_empty_success_response_returns_none() -> None:
    with patch("urllib.request.urlopen", return_value=EmptyResponse()):
        client = CimaClient("https://example.test", delay=0)
        assert client.get("empty") is None
