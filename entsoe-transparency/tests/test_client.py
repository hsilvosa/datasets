from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from entsoe_transparency.client import EntsoeResponseError, inspect_response, load_token


class ClientTests(unittest.TestCase):
    def test_loads_token_from_env_file_without_returning_key_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("ENTSOE_API_TOKEN=secret-value\n", encoding="utf-8")
            self.assertEqual(load_token("ENTSOE_API_TOKEN", path), "secret-value")

    def test_detects_no_data_acknowledgement(self):
        xml = b"""<?xml version="1.0"?>
        <Acknowledgement_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:8:1">
          <Reason><code>999</code><text>No matching data found.</text></Reason>
        </Acknowledgement_MarketDocument>"""
        response = inspect_response(xml)
        self.assertEqual(response.status, "no_data")

    def test_rejected_response_has_sanitized_error(self):
        xml = b"""<?xml version="1.0"?>
        <Acknowledgement_MarketDocument><Reason><code>999</code>
        <text>Authentication failed.</text></Reason></Acknowledgement_MarketDocument>"""
        with self.assertRaises(EntsoeResponseError) as raised:
            inspect_response(xml)
        self.assertNotIn("secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
