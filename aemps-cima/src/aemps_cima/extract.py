from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from hashlib import sha256
from math import ceil
from pathlib import Path
from typing import Any, TypeVar

from .client import CimaClient
from .config import Config
from .io_utils import append_jsonl, atomic_json, read_jsonl, repair_jsonl, write_jsonl_atomic

MASTER_TABLES = {
    1: "active_ingredients",
    3: "pharmaceutical_forms",
    4: "administration_routes",
    6: "laboratories",
    7: "atc_codes",
    11: "active_ingredients_snomed",
    13: "pharmaceutical_forms_snomed",
    14: "administration_routes_snomed",
    15: "medications_snomed",
    16: "marketed_medications_snomed",
}

T = TypeVar("T")


def _existing_ids(path: Path, key: str) -> set[str]:
    return {str(row.get(key)) for row in read_jsonl(path) if row.get(key) is not None}


def _limit(rows: Iterable[dict], maximum: int | None) -> list[dict]:
    output = []
    for row in rows:
        output.append(row)
        if maximum is not None and len(output) >= maximum:
            break
    return output


def _parallel_map(
    function: Callable[[T], dict[str, Any]], tasks: Iterable[T], max_workers: int
) -> Iterator[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="cima-fetch") as executor:
        yield from executor.map(function, tasks)


def _append_in_batches(path: Path, rows: Iterable[dict[str, Any]], batch_size: int = 100) -> int:
    total = 0
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            total += append_jsonl(path, batch)
            batch.clear()
    if batch:
        total += append_jsonl(path, batch)
    return total


def _change_page_path(checkpoint_dir: Path, page: int) -> Path:
    return checkpoint_dir / f"{page:06d}.ndjson"


def _valid_change_page(path: Path, expected_rows: int) -> bool:
    if not path.exists():
        return False
    try:
        return sum(1 for _ in read_jsonl(path)) == expected_rows
    except (OSError, ValueError):
        return False


def _change_rows(payload: Any, page: int) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("resultados"), list):
        raise TypeError(f"Invalid change-register response for page {page}")
    return payload["resultados"]


def _import_legacy_change_stream(raw_dir: Path, checkpoint_dir: Path, page_size: int) -> int:
    """Convert a legacy interrupted monolithic stream into complete page checkpoints."""
    legacy_path = raw_dir / "changes.ndjson.tmp"
    if not legacy_path.exists() or any(checkpoint_dir.glob("[0-9]*.ndjson")):
        return 0
    page = 1
    batch: list[dict[str, Any]] = []
    for row in read_jsonl(legacy_path):
        batch.append(row)
        if len(batch) == page_size:
            write_jsonl_atomic(_change_page_path(checkpoint_dir, page), batch)
            page += 1
            batch.clear()
    return page - 1


def _download_change_register_pages(client: CimaClient, config: Config) -> tuple[Path, int]:
    """Download change-register pages concurrently with durable per-page checkpoints."""
    checkpoint_dir = config.raw_dir / "change_pages"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    first_payload = client.get("registroCambios", pagina=1, fecha=config.changes_since)
    first_rows = _change_rows(first_payload, 1)
    total_rows = int(first_payload.get("totalFilas") or len(first_rows))
    page_size = int(first_payload.get("tamanioPagina") or len(first_rows))
    if page_size <= 0:
        raise RuntimeError("CIMA returned an invalid change-register page size")

    source_pages = ceil(total_rows / page_size)
    total_pages = min(source_pages, config.max_pages) if config.max_pages else source_pages
    expected_total = min(total_rows, total_pages * page_size)
    atomic_json(
        checkpoint_dir / "manifest.json",
        {
            "changes_since": config.changes_since,
            "page_size": page_size,
            "source_total_rows": total_rows,
            "total_pages": total_pages,
            "expected_rows": expected_total,
        },
    )

    imported_pages = _import_legacy_change_stream(config.raw_dir, checkpoint_dir, page_size)
    if imported_pages:
        print(
            f"Change register: imported {imported_pages} complete legacy pages",
            file=sys.stderr,
            flush=True,
        )

    def expected_rows(page: int) -> int:
        if page == source_pages:
            return total_rows - page_size * (source_pages - 1)
        return page_size

    first_path = _change_page_path(checkpoint_dir, 1)
    if not _valid_change_page(first_path, expected_rows(1)):
        write_jsonl_atomic(first_path, first_rows)

    missing_pages = [
        page
        for page in range(2, total_pages + 1)
        if not _valid_change_page(_change_page_path(checkpoint_dir, page), expected_rows(page))
    ]
    completed = total_pages - len(missing_pages)
    print(
        f"Change register: {completed}/{total_pages} pages available; "
        f"downloading {len(missing_pages)} with {config.change_register_workers} workers",
        file=sys.stderr,
        flush=True,
    )

    def fetch_page(page: int) -> tuple[int, list[dict[str, Any]]]:
        payload = client.get("registroCambios", pagina=page, fecha=config.changes_since)
        rows = _change_rows(payload, page)
        wanted = expected_rows(page)
        if len(rows) != wanted:
            raise RuntimeError(
                f"Change-register page {page} returned {len(rows)} rows; expected {wanted}"
            )
        return page, rows

    if missing_pages:
        workers = max(1, min(config.change_register_workers, len(missing_pages)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cima-changes") as executor:
            futures = {executor.submit(fetch_page, page): page for page in missing_pages}
            for future in as_completed(futures):
                page, rows = future.result()
                write_jsonl_atomic(_change_page_path(checkpoint_dir, page), rows)
                completed += 1
                if completed % 50 == 0 or completed == total_pages:
                    print(
                        f"Change register: {completed}/{total_pages} pages complete",
                        file=sys.stderr,
                        flush=True,
                    )

    changes_path = config.raw_dir / "changes.ndjson"

    def checkpoint_rows() -> Iterator[dict[str, Any]]:
        for page in range(1, total_pages + 1):
            yield from read_jsonl(_change_page_path(checkpoint_dir, page))

    change_count = write_jsonl_atomic(changes_path, checkpoint_rows())
    if change_count != expected_total:
        raise RuntimeError(
            f"Merged change register contains {change_count} rows; expected {expected_total}"
        )
    return changes_path, change_count


def _change_checkpoint_path(checkpoint_dir: Path, registration: str) -> Path:
    digest = sha256(registration.encode("utf-8")).hexdigest()
    return checkpoint_dir / f"{digest}.ndjson"


def _valid_change_checkpoint(path: Path, registration: str) -> bool:
    if not path.exists():
        return False
    try:
        return all(str(row.get("nregistro")) == registration for row in read_jsonl(path))
    except (OSError, ValueError):
        return False


def _download_change_register(client: CimaClient, config: Config) -> tuple[Path, int]:
    """Download changes by registration with durable per-medication checkpoints."""
    checkpoint_dir = config.raw_dir / "change_registers"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    registrations = sorted(
        {
            str(row["nregistro"])
            for row in read_jsonl(config.raw_dir / "medication_index.ndjson")
            if row.get("nregistro") is not None
        }
    )
    if not registrations:
        raise RuntimeError("The medication index contains no registration numbers")
    atomic_json(
        checkpoint_dir / "manifest.json",
        {
            "changes_since": config.changes_since,
            "registration_count": len(registrations),
            "strategy": "one filtered query per registration",
        },
    )

    missing_registrations = [
        registration
        for registration in registrations
        if not _valid_change_checkpoint(
            _change_checkpoint_path(checkpoint_dir, registration), registration
        )
    ]
    completed = len(registrations) - len(missing_registrations)
    print(
        f"Change register: {completed}/{len(registrations)} medications available; "
        f"downloading {len(missing_registrations)} with "
        f"{config.change_register_workers} workers",
        file=sys.stderr,
        flush=True,
    )

    def fetch_registration(registration: str) -> tuple[str, list[dict[str, Any]]]:
        rows = list(
            client.paginated(
                "registroCambios",
                max_pages=config.max_pages,
                fecha=config.changes_since,
                nregistro=registration,
            )
        )
        if any(str(row.get("nregistro")) != registration for row in rows):
            raise RuntimeError(
                f"CIMA returned another medication while filtering for {registration}"
            )
        return registration, rows

    if missing_registrations:
        workers = max(1, min(config.change_register_workers, len(missing_registrations)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cima-changes") as executor:
            futures = {
                executor.submit(fetch_registration, registration): registration
                for registration in missing_registrations
            }
            for future in as_completed(futures):
                registration, rows = future.result()
                write_jsonl_atomic(_change_checkpoint_path(checkpoint_dir, registration), rows)
                completed += 1
                if completed % 100 == 0 or completed == len(registrations):
                    print(
                        f"Change register: {completed}/{len(registrations)} medications complete",
                        file=sys.stderr,
                        flush=True,
                    )

    changes_path = config.raw_dir / "changes.ndjson"

    def checkpoint_rows() -> Iterator[dict[str, Any]]:
        for registration in registrations:
            yield from read_jsonl(_change_checkpoint_path(checkpoint_dir, registration))

    change_count = write_jsonl_atomic(changes_path, checkpoint_rows())
    return changes_path, change_count


def download(config: Config) -> dict[str, int]:
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    client = CimaClient(
        config.base_url,
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
        delay=config.request_delay_seconds,
        user_agent=config.user_agent,
    )
    counts: dict[str, int] = {}

    index_path = config.raw_dir / "medication_index.ndjson"
    if not index_path.exists():
        index = _limit(
            client.paginated("medicamentos", max_pages=config.max_pages),
            config.max_medications,
        )
        counts["medication_index"] = append_jsonl(index_path, index)
    else:
        index = list(read_jsonl(index_path))
        counts["medication_index"] = len(index)

    details_path = config.raw_dir / "medications.ndjson"
    repair_jsonl(details_path, "nregistro")
    completed = _existing_ids(details_path, "nregistro")
    if config.include_details:
        registrations = [
            str(item["nregistro"]) for item in index if str(item["nregistro"]) not in completed
        ]

        def fetch_detail(registration: str) -> dict[str, Any]:
            return client.get("medicamento", nregistro=registration)

        _append_in_batches(
            details_path,
            _parallel_map(fetch_detail, registrations, config.max_workers),
        )
    elif not details_path.exists():
        append_jsonl(details_path, index)
    repair_jsonl(details_path, "nregistro")
    counts["medications"] = sum(1 for _ in read_jsonl(details_path))

    masters_path = config.raw_dir / "master_data.ndjson"
    masters_status_path = config.raw_dir / "master_data_status.json"
    if not masters_path.exists() and not masters_status_path.exists():
        master_counts = {}
        for master_id, master_name in MASTER_TABLES.items():
            payload = client.get("maestras", maestra=master_id, enuso=0)
            rows = payload if isinstance(payload, list) else (payload or {}).get("resultados", [])
            master_counts[master_name] = len(rows)
            append_jsonl(
                masters_path,
                ({"master_id": master_id, "master_name": master_name, **row} for row in rows),
            )
        atomic_json(
            masters_status_path,
            {
                "retrieved_at": datetime.now(UTC).isoformat(),
                "counts": master_counts,
                "note": "Zero counts reflect HTTP 204 responses from the documented endpoint.",
            },
        )
    counts["master_data"] = sum(1 for _ in read_jsonl(masters_path))

    if config.include_documents:
        documents_path = config.raw_dir / "documents.ndjson"
        document_keys = {
            (str(row.get("nregistro")), int(row.get("document_type", 0)))
            for row in read_jsonl(documents_path)
        }
        document_tasks = []
        for medication in read_jsonl(details_path):
            registration = str(medication["nregistro"])
            available_types = {
                int(document.get("tipo"))
                for document in medication.get("docs", [])
                if document.get("secc") and document.get("tipo") in (1, 2)
            }
            for document_type in sorted(available_types):
                if (registration, document_type) in document_keys:
                    continue
                document_tasks.append((registration, document_type))

        def fetch_document(task: tuple[str, int]) -> dict[str, Any]:
            registration, document_type = task
            sections = client.get(
                f"docSegmentado/contenido/{document_type}", nregistro=registration
            )
            return {
                "nregistro": registration,
                "document_type": document_type,
                "sections": sections or [],
            }

        _append_in_batches(
            documents_path,
            _parallel_map(fetch_document, document_tasks, config.max_workers),
        )
        counts["document_responses"] = sum(1 for _ in read_jsonl(documents_path))

    if config.include_change_register:
        changes_path = config.raw_dir / "changes.ndjson"
        changes_status_path = config.raw_dir / "changes_status.json"
        if not changes_status_path.exists():
            changes_path, change_count = _download_change_register(client, config)
            atomic_json(
                changes_status_path,
                {
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "changes_since": config.changes_since,
                    "source_event_count": change_count,
                },
            )
        counts["change_events"] = sum(1 for _ in read_jsonl(changes_path))

    atomic_json(
        config.raw_dir / "snapshot.json",
        {
            "retrieved_at": datetime.now(UTC).isoformat(),
            "base_url": config.base_url,
            "api_documentation_version": "1.23",
            "counts": counts,
        },
    )
    return counts
