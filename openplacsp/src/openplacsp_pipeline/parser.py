from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO


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
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def text_child(element: ET.Element | None, name: str) -> str | None:
    return text(child(element, name))


def number(element: ET.Element | None) -> float | None:
    value = text(element)
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def integer(element: ET.Element | None) -> int | None:
    value = number(element)
    return int(value) if value is not None else None


def identifier(party: ET.Element | None, scheme: str) -> str | None:
    for group in descendants(party, "PartyIdentification"):
        candidate = child(group, "ID")
        if candidate is not None and candidate.attrib.get("schemeName") == scheme:
            return text(candidate)
    return None


def money(parent: ET.Element | None, name: str) -> tuple[float | None, str | None]:
    element = descendant(parent, name)
    return number(element), element.attrib.get("currencyID") if element is not None else None


@dataclass
class ParsedEntry:
    version: dict
    lots: list[dict]
    cpv_codes: list[dict]
    awards: list[dict]


def _version_id(atom_id: str | None, updated: str | None, deleted: bool) -> str:
    key = f"{atom_id or ''}\x1f{updated or ''}\x1f{int(deleted)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def parse_entry(entry: ET.Element, *, source_archive: str, source_member: str) -> ParsedEntry:
    deleted = local_name(entry.tag) == "deleted-entry"
    atom_id = entry.attrib.get("ref") if deleted else text_child(entry, "id")
    updated = entry.attrib.get("when") if deleted else text_child(entry, "updated")
    version_id = _version_id(atom_id, updated, deleted)
    status = descendant(entry, "ContractFolderStatus")
    project = child(status, "ProcurementProject")
    budget = child(project, "BudgetAmount")
    party_container = descendant(status, "LocatedContractingParty")
    party = child(party_container, "Party")
    party_name = text(descendant(child(party, "PartyName"), "Name"))
    estimated_value, estimated_currency = money(budget, "EstimatedOverallContractAmount")
    tax_exclusive, tax_currency = money(budget, "TaxExclusiveAmount")
    total_amount, total_currency = money(budget, "TotalAmount")
    link = next(
        (
            item.attrib.get("href")
            for item in entry
            if local_name(item.tag) == "link" and item.attrib.get("href")
        ),
        None,
    )
    version = {
        "version_id": version_id,
        "atom_id": atom_id,
        "updated_at": updated,
        "published_at": text_child(entry, "published"),
        "title": text_child(entry, "title"),
        "summary": text_child(entry, "summary"),
        "entry_url": link,
        "is_deleted": deleted,
        "folder_id": text_child(status, "ContractFolderID"),
        "status_code": text(descendant(status, "ContractFolderStatusCode")),
        "project_name": text_child(project, "Name"),
        "contract_type_code": text_child(project, "TypeCode"),
        "contract_subtype_code": text_child(project, "SubTypeCode"),
        "estimated_value": estimated_value,
        "budget_tax_exclusive": tax_exclusive,
        "budget_total": total_amount,
        "currency": estimated_currency or tax_currency or total_currency,
        "procedure_code": text(descendant(child(status, "TenderingProcess"), "ProcedureCode")),
        "contracting_party_name": party_name,
        "contracting_party_nif": identifier(party, "NIF"),
        "contracting_party_platform_id": identifier(party, "ID_PLATAFORMA"),
        "contracting_party_type_code": text_child(party_container, "ContractingPartyTypeCode"),
        "buyer_profile_url": text_child(party_container, "BuyerProfileURIID"),
        "source_archive": source_archive,
        "source_member": source_member,
    }
    lots: list[dict] = []
    cpv_codes: list[dict] = []
    for classification in descendants(project, "RequiredCommodityClassification"):
        code = child(classification, "ItemClassificationCode")
        if text(code):
            cpv_codes.append(
                {
                    "version_id": version_id,
                    "lot_id": None,
                    "cpv_code": text(code),
                    "cpv_name": code.attrib.get("name") if code is not None else None,
                }
            )
    for position, lot in enumerate(descendants(status, "ProcurementProjectLot"), 1):
        lot_project = child(lot, "ProcurementProject")
        lot_id = text_child(lot, "ID") or str(position)
        lot_budget = child(lot_project, "BudgetAmount")
        lot_tax, lot_tax_currency = money(lot_budget, "TaxExclusiveAmount")
        lot_total, lot_total_currency = money(lot_budget, "TotalAmount")
        lots.append(
            {
                "version_id": version_id,
                "lot_id": lot_id,
                "name": text_child(lot_project, "Name"),
                "budget_tax_exclusive": lot_tax,
                "budget_total": lot_total,
                "currency": lot_tax_currency or lot_total_currency,
            }
        )
        for classification in descendants(lot_project, "RequiredCommodityClassification"):
            code = child(classification, "ItemClassificationCode")
            if text(code):
                cpv_codes.append(
                    {
                        "version_id": version_id,
                        "lot_id": lot_id,
                        "cpv_code": text(code),
                        "cpv_name": code.attrib.get("name") if code is not None else None,
                    }
                )
    awards: list[dict] = []
    for result_position, result in enumerate(descendants(status, "TenderResult"), 1):
        awarded = child(result, "AwardedTenderedProject")
        award_amount, award_currency = money(
            child(awarded, "LegalMonetaryTotal"), "TaxExclusiveAmount"
        )
        winners = descendants(result, "WinningParty") or [None]
        for winner_position, winner in enumerate(winners, 1):
            winner_name = text(descendant(child(winner, "PartyName"), "Name"))
            awards.append(
                {
                    "version_id": version_id,
                    "result_position": result_position,
                    "winner_position": winner_position,
                    "result_code": text_child(result, "ResultCode"),
                    "description": text_child(result, "Description"),
                    "award_date": text_child(result, "AwardDate"),
                    "received_tenders": integer(child(result, "ReceivedTenderQuantity")),
                    "lot_id": text_child(awarded, "ProcurementProjectLotID"),
                    "winner_name": winner_name,
                    "winner_nif": identifier(winner, "NIF"),
                    "award_tax_exclusive": award_amount,
                    "currency": award_currency,
                }
            )
    return ParsedEntry(version, lots, cpv_codes, awards)


def iter_entries(
    handle: BinaryIO, *, source_archive: str, source_member: str
) -> Iterator[ParsedEntry]:
    for _, element in ET.iterparse(handle, events=("end",)):
        if local_name(element.tag) in {"entry", "deleted-entry"}:
            yield parse_entry(element, source_archive=source_archive, source_member=source_member)
            element.clear()
