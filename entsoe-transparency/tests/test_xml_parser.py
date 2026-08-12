from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from entsoe_transparency.config import Zone
from entsoe_transparency.xml_parser import parse_document

PRICE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <mRID>document-1</mRID><revisionNumber>1</revisionNumber>
  <TimeSeries><mRID>series-1</mRID><businessType>A62</businessType>
    <contract_MarketAgreement.type>A01</contract_MarketAgreement.type>
    <auction.type>A01</auction.type>
    <classificationSequence_AttributeInstanceComponent.position>1</classificationSequence_AttributeInstanceComponent.position>
    <currency_Unit.name>EUR</currency_Unit.name>
    <price_Measure_Unit.name>MWH</price_Measure_Unit.name><curveType>A01</curveType>
    <Period><timeInterval><start>2025-01-01T00:00Z</start><end>2025-01-01T02:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>50.5</price.amount></Point>
      <Point><position>2</position><price.amount>-2.0</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""

LOAD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <mRID>document-2</mRID><revisionNumber>2</revisionNumber>
  <TimeSeries><mRID>series-2</mRID><quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>
    <curveType>A01</curveType><Period>
      <timeInterval><start>2025-01-01T00:00Z</start><end>2025-01-01T00:30Z</end></timeInterval>
      <resolution>PT15M</resolution>
      <Point><position>1</position><quantity>100.0</quantity></Point>
      <Point><position>2</position><quantity>101.0</quantity></Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.zone = Zone("ES", "Spain", "ES", "10YES-REE------0")

    def parse(self, xml: str, dataset: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "response.xml"
            path.write_text(xml, encoding="utf-8")
            return list(parse_document(path, dataset, self.zone))

    def test_parses_hourly_prices_and_preserves_negative_values(self):
        rows = self.parse(PRICE_XML, "day_ahead_prices")
        self.assertEqual([row["price"] for row in rows], [50.5, -2.0])
        self.assertEqual(rows[1]["timestamp_utc"].hour, 1)
        self.assertEqual(rows[0]["currency"], "EUR")

    def test_parses_quarter_hourly_load(self):
        rows = self.parse(LOAD_XML, "actual_load")
        self.assertEqual([row["load"] for row in rows], [100.0, 101.0])
        self.assertEqual(rows[1]["timestamp_utc"].minute, 15)
        self.assertEqual(rows[0]["unit"], "MAW")

    def test_record_identity_distinguishes_resolution_not_document_series(self):
        hourly = self.parse(PRICE_XML, "day_ahead_prices")[0]
        repeated_document = PRICE_XML.replace("series-1", "another-series")
        repeated = self.parse(repeated_document, "day_ahead_prices")[0]
        quarter_hour = self.parse(
            PRICE_XML.replace("PT60M", "PT15M"), "day_ahead_prices"
        )[0]
        self.assertEqual(hourly["record_id"], repeated["record_id"])
        self.assertNotEqual(hourly["record_id"], quarter_hour["record_id"])

    def test_intraday_contract_is_excluded_from_day_ahead_table(self):
        intraday = PRICE_XML.replace(
            "<contract_MarketAgreement.type>A01</contract_MarketAgreement.type>",
            "<contract_MarketAgreement.type>A07</contract_MarketAgreement.type>",
        )
        self.assertEqual(self.parse(intraday, "day_ahead_prices"), [])


if __name__ == "__main__":
    unittest.main()
