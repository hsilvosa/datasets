from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import Zone


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def direct(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in element if local_name(child.tag) == name), None)


def direct_text(element: ET.Element, name: str) -> str | None:
    child = direct(element, name)
    return child.text.strip() if child is not None and child.text else None


def nested_text(element: ET.Element, *names: str) -> str | None:
    current = element
    for name in names:
        child = direct(current, name)
        if child is None:
            return None
        current = child
    return current.text.strip() if current.text else None


def parse_duration(value: str) -> timedelta:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
    if not match:
        raise ValueError(f"Unsupported ENTSO-E resolution: {value}")
    hours, minutes, seconds = (int(item or 0) for item in match.groups())
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC)


def _record_id(
    dataset: str,
    zone_key: str,
    timestamp: datetime,
    resolution: str,
    business_type: str | None,
    contract_type: str | None,
    auction_type: str | None,
    classification_position: int | None,
) -> str:
    payload = "|".join(
        str(value or "")
        for value in (
            dataset,
            zone_key,
            timestamp.isoformat(),
            resolution,
            business_type,
            contract_type,
            auction_type,
            classification_position,
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def parse_document(
    path: Path,
    dataset: str,
    zone: Zone,
    source_name: str | None = None,
) -> Iterator[dict[str, Any]]:
    root = ET.parse(path).getroot()
    if local_name(root.tag) == "Acknowledgement_MarketDocument":
        return
    document_id = direct_text(root, "mRID")
    revision_text = direct_text(root, "revisionNumber")
    revision = int(revision_text) if revision_text and revision_text.isdigit() else None
    for series in (element for element in root if local_name(element.tag) == "TimeSeries"):
        series_id = direct_text(series, "mRID") or ""
        business_type = direct_text(series, "businessType")
        contract_type = direct_text(series, "contract_MarketAgreement.type")
        auction_type = direct_text(series, "auction.type")
        classification_text = direct_text(
            series, "classificationSequence_AttributeInstanceComponent.position"
        )
        classification_position = int(classification_text) if classification_text else None
        if dataset == "day_ahead_prices" and contract_type not in {None, "A01"}:
            continue
        unit = direct_text(series, "quantity_Measure_Unit.name")
        if dataset == "day_ahead_prices":
            unit = direct_text(series, "price_Measure_Unit.name") or unit
        currency = direct_text(series, "currency_Unit.name")
        curve_type = direct_text(series, "curveType")
        for period in (element for element in series if local_name(element.tag) == "Period"):
            start_text = nested_text(period, "timeInterval", "start")
            resolution = direct_text(period, "resolution")
            if not start_text or not resolution:
                continue
            start = parse_timestamp(start_text)
            step = parse_duration(resolution)
            for point in (element for element in period if local_name(element.tag) == "Point"):
                position_text = direct_text(point, "position")
                value_text = (
                    direct_text(point, "price.amount")
                    if dataset == "day_ahead_prices"
                    else direct_text(point, "quantity")
                )
                if not position_text or value_text is None:
                    continue
                timestamp = start + step * (int(position_text) - 1)
                row: dict[str, Any] = {
                    "record_id": _record_id(
                        dataset,
                        zone.key,
                        timestamp,
                        resolution,
                        business_type,
                        contract_type,
                        auction_type,
                        classification_position,
                    ),
                    "timestamp_utc": timestamp,
                    "zone_key": zone.key,
                    "zone_name": zone.name,
                    "country_code": zone.country_code,
                    "eic_code": zone.eic_code,
                    "unit": unit,
                    "resolution": resolution,
                    "curve_type": curve_type,
                    "business_type": business_type,
                    "contract_type": contract_type,
                    "auction_type": auction_type,
                    "classification_position": classification_position,
                    "document_id": document_id,
                    "revision_number": revision,
                    "timeseries_id": series_id,
                    "source_file": source_name or path.name,
                }
                if dataset == "day_ahead_prices":
                    row["price"] = float(value_text)
                    row["currency"] = currency
                else:
                    row["load"] = float(value_text)
                yield row
