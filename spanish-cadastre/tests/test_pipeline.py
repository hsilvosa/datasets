from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pyarrow.parquet as pq
from shapely import from_wkb

from spanish_cadastre.gml import SourceContext, parse_feature


def test_direct_polygon_and_href_values() -> None:
    feature = ET.fromstring(
        """<bu:OtherConstruction xmlns:bu="urn:bu" xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:base="urn:base" xmlns:xlink="http://www.w3.org/1999/xlink" gml:id="oc-1">
        <base:Identifier><base:localId>oc-1</base:localId><base:namespace>ES.TEST</base:namespace></base:Identifier>
        <bu:conditionOfConstruction xlink:href="urn:condition:functional" />
        <bu:geometry><gml:Polygon srsName="urn:ogc:def:crs:EPSG::4326"><gml:exterior><gml:LinearRing><gml:posList srsDimension="2">-1 39 0 39 0 40 -1 39</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></bu:geometry>
        </bu:OtherConstruction>"""
    )
    table, row = parse_feature(feature, SourceContext("02", "02001", "ABENGIBRE", "a.zip", "a.gml"))
    assert table == "other_constructions"
    assert row["condition_of_construction"] == "urn:condition:functional"
    assert from_wkb(row["geometry"]).bounds == (-1.0, 39.0, 0.0, 40.0)


def test_official_pilot_quality_and_card() -> None:
    root = Path(__file__).resolve().parents[1]
    quality = json.loads((root / "artifacts/sample/quality.json").read_text(encoding="utf-8"))
    assert quality["checks_passed"] is True
    assert all(item["null_required_values"] == 0 for item in quality["tables"].values())
    municipality = pq.read_table(root / "data/sample/processed/municipalities").to_pylist()
    assert municipality[0]["municipality_name"] == "ABENGIBRE"
    card = (root / "hf_staging_sample/README.md").read_text(encoding="utf-8")
    assert "## Dataset description" in card
    assert "## Data structure" in card
    assert "No API key" not in card
