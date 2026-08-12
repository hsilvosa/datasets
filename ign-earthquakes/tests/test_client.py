import unittest
from unittest.mock import patch

from ign_earthquakes.client import PREFIX, IgnClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return b"Evento;Fecha\n"


class ClientTests(unittest.TestCase):
    @patch("urllib.request.urlopen", return_value=FakeResponse())
    def test_download_uses_official_form_fields(self, mocked_open):
        client = IgnClient("https://example.test/download", delay=0)
        result = client.download_csv({"startDate": "01/08/2026"})
        request = mocked_open.call_args.args[0]
        self.assertEqual(result, b"Evento;Fecha\n")
        self.assertEqual(request.method, "POST")
        self.assertIn(f'{PREFIX}startDate'.encode(), request.data)
        self.assertIn(f'{PREFIX}tipoDescarga'.encode(), request.data)
        self.assertNotIn(b"token", request.data.lower())


if __name__ == "__main__":
    unittest.main()
