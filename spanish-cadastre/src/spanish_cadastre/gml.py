from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import BinaryIO

from pyproj import CRS, Transformer
from shapely import MultiPolygon, Point, Polygon, to_wkb

FEATURE_TABLES = {
    "CadastralParcel": "cadastral_parcels",
    "CadastralZoning": "cadastral_zonings",
    "Address": "addresses",
    "Building": "buildings",
    "BuildingPart": "building_parts",
    "OtherConstruction": "other_constructions",
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    return next((item for item in element if local_name(item.tag) == name), None)


def descendants(element: ET.Element | None, name: str) -> list[ET.Element]:
    if element is None:
        return []
    return [item for item in element.iter() if local_name(item.tag) == name]


def descendant(element: ET.Element | None, name: str) -> ET.Element | None:
    return next(iter(descendants(element, name)), None)


def text(element: ET.Element | None) -> str | None:
    value = element.text.strip() if element is not None and element.text else ""
    return value or None


def text_desc(element: ET.Element | None, name: str) -> str | None:
    return text(descendant(element, name))


def value_desc(element: ET.Element | None, name: str) -> str | None:
    item = descendant(element, name)
    if item is None:
        return None
    value = text(item)
    if value:
        return value
    return next(
        (attribute for key, attribute in item.attrib.items() if local_name(key) == "href"),
        None,
    )


def number(element: ET.Element | None, name: str) -> float | None:
    value = text_desc(element, name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def integer(element: ET.Element | None, name: str) -> int | None:
    value = number(element, name)
    return int(value) if value is not None else None


def hrefs(element: ET.Element | None, name: str) -> list[str]:
    result: list[str] = []
    for item in descendants(element, name):
        href = next((value for key, value in item.attrib.items() if local_name(key) == "href"), None)
        if href:
            result.append(href)
    return result


def epsg_code(element: ET.Element) -> int:
    for item in element.iter():
        value = item.attrib.get("srsName")
        if value:
            match = re.search(r"([0-9]{4,5})$", value)
            if match:
                return int(match.group(1))
    raise ValueError("Feature geometry has no supported EPSG code")


@lru_cache(maxsize=16)
def transformer(epsg: int) -> Transformer:
    return Transformer.from_crs(CRS.from_epsg(epsg), CRS.from_epsg(4326), always_xy=True)


def coordinates(pos_list: ET.Element | None) -> list[tuple[float, float]]:
    if pos_list is None or not text(pos_list):
        return []
    values = [float(value) for value in text(pos_list).replace(",", " ").split()]
    dimension = int(pos_list.attrib.get("srsDimension", 2))
    return [(values[index], values[index + 1]) for index in range(0, len(values), dimension)]


def transformed(points: list[tuple[float, float]], epsg: int) -> list[tuple[float, float]]:
    if not points:
        return []
    xs, ys = zip(*points, strict=True)
    longitudes, latitudes = transformer(epsg).transform(xs, ys)
    return list(zip(longitudes, latitudes, strict=True))


def geometry(element: ET.Element) -> tuple[bytes | None, tuple[float, float, float, float] | None, str]:
    epsg = epsg_code(element)
    source_crs = f"EPSG:{epsg}"
    point = descendant(element, "Point")
    polygons_or_patches = descendants(element, "PolygonPatch") or descendants(element, "Polygon")
    if point is not None and not polygons_or_patches:
        pos = coordinates(descendant(point, "pos"))
        if not pos:
            return None, None, source_crs
        shape = Point(transformed(pos, epsg)[0])
    else:
        polygons = []
        for patch in polygons_or_patches:
            exterior_container = child(patch, "exterior")
            exterior = transformed(
                coordinates(descendant(exterior_container, "posList")), epsg
            )
            if len(exterior) < 4:
                continue
            holes = [
                transformed(coordinates(descendant(interior, "posList")), epsg)
                for interior in (item for item in patch if local_name(item.tag) == "interior")
            ]
            polygons.append(Polygon(exterior, [ring for ring in holes if len(ring) >= 4]))
        if not polygons:
            return None, None, source_crs
        shape = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    return to_wkb(shape, output_dimension=2), shape.bounds, source_crs


def properties(element: ET.Element) -> str:
    ignored = {"pos", "posList", "lowerCorner", "upperCorner"}
    values: dict[str, str | list[str]] = {}
    for item in element.iter():
        name = local_name(item.tag)
        value = text(item)
        if len(item) or not value or name in ignored:
            continue
        if name in values:
            previous = values[name]
            values[name] = [*previous, value] if isinstance(previous, list) else [previous, value]
        else:
            values[name] = value
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class SourceContext:
    province_code: str
    municipality_code: str
    municipality_name: str
    source_archive: str
    source_member: str


def parse_feature(element: ET.Element, context: SourceContext) -> tuple[str, dict]:
    feature_type = local_name(element.tag)
    identifier = descendant(element, "Identifier")
    geometry_wkb, bounds, source_crs = geometry(element)
    row = {
        "feature_id": element.attrib.get("{http://www.opengis.net/gml/3.2}id")
        or text_desc(identifier, "localId"),
        "local_id": text_desc(identifier, "localId"),
        "namespace": text_desc(identifier, "namespace"),
        "province_code": context.province_code,
        "municipality_code": context.municipality_code,
        "municipality_name": context.municipality_name,
        "begin_lifespan_version": text_desc(element, "beginLifespanVersion"),
        "end_lifespan_version": text_desc(element, "endLifespanVersion"),
        "source_crs": source_crs,
        "geometry": geometry_wkb,
        "bbox_min_x": bounds[0] if bounds else None,
        "bbox_min_y": bounds[1] if bounds else None,
        "bbox_max_x": bounds[2] if bounds else None,
        "bbox_max_y": bounds[3] if bounds else None,
        "properties_json": properties(element),
        "source_archive": context.source_archive,
        "source_member": context.source_member,
    }
    if feature_type == "CadastralParcel":
        row.update(
            area_value=number(element, "areaValue"),
            label=text_desc(element, "label"),
            national_reference=text_desc(element, "nationalCadastralReference"),
        )
    elif feature_type == "CadastralZoning":
        row.update(
            estimated_accuracy=number(element, "estimatedAccuracy"),
            label=text_desc(element, "label"),
            level=text_desc(element, "level"),
            level_name=text_desc(element, "levelName"),
            national_reference=text_desc(element, "nationalCadastalZoningReference"),
            original_scale_denominator=integer(element, "originalMapScaleDenominator"),
        )
    elif feature_type == "Address":
        row.update(
            locator_designator=text_desc(element, "designator"),
            valid_from=text_desc(element, "validFrom"),
            valid_to=text_desc(element, "validTo"),
        )
    else:
        row.update(
            condition_of_construction=value_desc(element, "conditionOfConstruction"),
            construction_begin=text_desc(descendant(element, "dateOfConstruction"), "beginning"),
            construction_end=text_desc(descendant(element, "dateOfConstruction"), "end"),
            current_use=value_desc(element, "currentUse"),
            number_of_building_units=integer(element, "numberOfBuildingUnits"),
            number_of_dwellings=integer(element, "numberOfDwellings"),
            floors_above_ground=integer(element, "numberOfFloorsAboveGround"),
            floors_below_ground=integer(element, "numberOfFloorsBelowGround"),
            official_area=number(element, "officialArea"),
            cadastral_parcel_refs=hrefs(element, "cadastralParcels"),
            address_refs=hrefs(element, "addresses"),
        )
    return FEATURE_TABLES[feature_type], row


def iter_features(handle: BinaryIO, context: SourceContext) -> Iterator[tuple[str, dict]]:
    for _, element in ET.iterparse(handle, events=("end",)):
        if local_name(element.tag) in FEATURE_TABLES:
            yield parse_feature(element, context)
            element.clear()
