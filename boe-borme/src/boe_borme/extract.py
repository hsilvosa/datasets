from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import layout
from .client import BoeClient, RateLimiter
from .config import Config
from .io_utils import append_jsonl, atomic_bytes, atomic_json, read_json
from .parser import xml_payload, xml_status_code

CATALOG_PAGE = 10_000


@dataclass(frozen=True)
class Unit:
    dataset: str
    unit: str
    url: str
    kind: str
    payload: dict | None = field(default=None, compare=False)


def to_date8(value: date) -> str:
    return value.strftime("%Y%m%d")


def daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def fetch_catalog(client: BoeClient, config: Config) -> list[dict]:
    items: dict[str, dict] = {}
    offset = 0
    while True:
        url = (
            f"{config.base_url}/datosabiertos/api/legislacion-consolidada"
            f"?limit={CATALOG_PAGE}&offset={offset}"
        )
        response = client.get(url, accept="application/json")
        if response.status != 200:
            break
        payload = json.loads(response.text())
        if str((payload.get("status") or {}).get("code")) != "200":
            break
        page = payload.get("data") or []
        if not page:
            break
        for item in page:
            identifier = item.get("identificador")
            if identifier:
                items[identifier] = item
        print(f"  catalog: {len(items):,} norms", file=sys.stderr)
        if len(page) < CATALOG_PAGE:
            break
        offset += CATALOG_PAGE
    atomic_json(
        layout.catalog_path(config.raw_dir),
        {
            "retrieved_at_utc": datetime.now(UTC).isoformat(),
            "count": len(items),
            "items": sorted(items.values(), key=lambda value: value["identificador"]),
        },
    )
    return list(items.values())


def _metadata_current(raw_dir: Path, norm_id: str, item: dict) -> bool:
    path = layout.norm_metadata_path(raw_dir, norm_id)
    if not path.exists():
        return False
    try:
        current = read_json(path)
    except (ValueError, OSError):
        return False
    return current.get("fecha_actualizacion") == item.get("fecha_actualizacion")


def build_plan(config: Config, catalog: list[dict]) -> dict[str, list[Unit]]:
    plan: dict[str, list[Unit]] = {}
    end = config.end()
    refresh_from = end - timedelta(days=config.refresh_days)
    force_refresh = config.refresh_days > 0

    if config.include_boe_sumario:
        units = [
            Unit(
                layout.BOE_SUMARIO,
                to_date8(day),
                f"{config.base_url}/datosabiertos/api/boe/sumario/{to_date8(day)}",
                "json",
            )
            for day in daterange(config.start_for(layout.BOE_SUMARIO), end)
            if (force_refresh and day > refresh_from)
            or not layout.is_date_complete(config.raw_dir, layout.BOE_SUMARIO, to_date8(day))
        ]
        plan[layout.BOE_SUMARIO] = _cap(units, config.max_units)

    if config.include_borme_sumario:
        units = [
            Unit(
                layout.BORME_SUMARIO,
                to_date8(day),
                f"{config.base_url}/datosabiertos/api/borme/sumario/{to_date8(day)}",
                "json",
            )
            for day in daterange(config.start_for(layout.BORME_SUMARIO), end)
            if (force_refresh and day > refresh_from)
            or not layout.is_date_complete(config.raw_dir, layout.BORME_SUMARIO, to_date8(day))
        ]
        plan[layout.BORME_SUMARIO] = _cap(units, config.max_units)

    if config.include_legislacion:
        units = []
        for item in catalog:
            norm_id = item["identificador"]
            if (
                not layout.is_metadata_complete(config.raw_dir, norm_id)
                or not layout.is_analisis_complete(config.raw_dir, norm_id)
                or not _metadata_current(config.raw_dir, norm_id, item)
            ):
                units.append(
                    Unit(
                        layout.BOE_LEGISLACION,
                        norm_id,
                        f"{config.base_url}/datosabiertos/api/legislacion-consolidada/id/{norm_id}/analisis",
                        "json",
                        payload=item,
                    )
                )
        plan[layout.BOE_LEGISLACION] = _cap(units, config.max_units)

    if config.include_legislacion and config.include_legislacion_texto:
        units = [
            Unit(
                layout.BOE_LEGISLACION_TEXTO,
                item["identificador"],
                f"{config.base_url}/datosabiertos/api/legislacion-consolidada/id/{item['identificador']}/texto",
                "xml",
            )
            for item in catalog
            if not layout.is_texto_complete(config.raw_dir, item["identificador"])
        ]
        plan[layout.BOE_LEGISLACION_TEXTO] = _cap(units, config.max_units)

    if config.include_aux:
        plan[layout.BOE_AUX] = [
            Unit(
                layout.BOE_AUX,
                name,
                f"{config.base_url}/datosabiertos/api/datos-auxiliares/{name}",
                "json",
            )
            for name in layout.AUX_TABLES
        ]

    return {name: units for name, units in plan.items() if units}


def _cap(units: list[Unit], limit: int | None) -> list[Unit]:
    return units if limit is None else units[:limit]


def _body_code(content: bytes) -> str:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return ""
    if isinstance(payload, dict):
        status = payload.get("status")
        if isinstance(status, dict):
            return str(status.get("code", ""))
    return ""


def _process_date(client: BoeClient, config: Config, unit: Unit) -> None:
    retrieved = datetime.now(UTC).isoformat()
    json_response = None
    try:
        json_response = client.get(unit.url, accept="application/json")
    except RuntimeError:
        json_response = None
    if json_response is not None:
        if json_response.status == 404:
            layout.mark_date_empty(config.raw_dir, unit.dataset, unit.unit, "http-404", retrieved)
            return
        if json_response.status == 200 and _body_code(json_response.content) == "200":
            layout.write_date_payload(config.raw_dir, unit.dataset, unit.unit, json_response.content)
            return

    # Some historical editions fail JSON serialization with HTTP 500; XML still works.
    xml_response = None
    try:
        xml_response = client.get(unit.url, accept="application/xml")
    except RuntimeError:
        xml_response = None
    if (
        xml_response is not None
        and xml_response.status == 200
        and xml_status_code(xml_response.content) == "200"
    ):
        payload = xml_payload(xml_response.content)
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        layout.write_date_payload(config.raw_dir, unit.dataset, unit.unit, content)
        xml_path = layout.date_dir(config.raw_dir, unit.dataset, unit.unit) / f"{unit.unit}.xml"
        atomic_bytes(xml_path, xml_response.content)
        atomic_json(
            layout.date_dir(config.raw_dir, unit.dataset, unit.unit) / f"{unit.unit}.fallback",
            {"retrieved_at_utc": retrieved, "method": "xml", "source_url": unit.url},
        )
        return

    reason = (
        f"json-{getattr(json_response, 'status', 'error')}"
        f"-xml-{getattr(xml_response, 'status', 'error')}"
    )
    layout.mark_date_empty(config.raw_dir, unit.dataset, unit.unit, reason, retrieved)


def _process_norm(client: BoeClient, config: Config, unit: Unit) -> None:
    item = unit.payload or {}
    layout.write_norm_metadata(config.raw_dir, unit.unit, item)
    retrieved = datetime.now(UTC).isoformat()
    response = client.get(unit.url, accept="application/json")
    if response.status != 200 or _body_code(response.content) != "200":
        layout.norm_analisis_empty(config.raw_dir, unit.unit).parent.mkdir(
            parents=True, exist_ok=True
        )
        atomic_json(
            layout.norm_analisis_empty(config.raw_dir, unit.unit),
            {"retrieved_at_utc": retrieved, "reason": f"status-{response.status}"},
        )
        return
    atomic_bytes(layout.norm_analisis_path(config.raw_dir, unit.unit), response.content)


def _process_texto(client: BoeClient, config: Config, unit: Unit) -> None:
    response = client.get(unit.url, accept="application/xml")
    retrieved = datetime.now(UTC).isoformat()
    if response.status != 200 or not response.content:
        atomic_json(
            layout.norm_texto_empty(config.raw_dir, unit.unit),
            {"retrieved_at_utc": retrieved, "reason": f"status-{response.status}"},
        )
        return
    atomic_bytes(layout.norm_texto_path(config.raw_dir, unit.unit), response.content)


def _process_aux(client: BoeClient, config: Config, unit: Unit) -> None:
    response = client.get(unit.url, accept="application/json")
    retrieved = datetime.now(UTC).isoformat()
    if response.status != 200 or not response.content:
        atomic_json(
            layout.aux_empty_marker(config.raw_dir, unit.unit),
            {"retrieved_at_utc": retrieved, "reason": f"status-{response.status}"},
        )
        return
    atomic_bytes(layout.aux_path(config.raw_dir, unit.unit), response.content)


PROCESSORS = {
    layout.BOE_SUMARIO: _process_date,
    layout.BORME_SUMARIO: _process_date,
    layout.BOE_LEGISLACION: _process_norm,
    layout.BOE_LEGISLACION_TEXTO: _process_texto,
    layout.BOE_AUX: _process_aux,
}


def _run_dataset(
    client: BoeClient, config: Config, dataset: str, units: list[Unit]
) -> dict[str, int]:
    processor = PROCESSORS[dataset]
    total = len(units)
    errors = 0
    done = 0
    started = time.monotonic()
    last_report = started
    lock = threading.Lock()

    def work(unit: Unit) -> tuple[str, str | None]:
        try:
            processor(client, config, unit)
            return unit.unit, None
        except Exception as exc:  # noqa: BLE001 - recorded and retried on next run
            return unit.unit, str(exc)

    print(f"[{dataset}] {total:,} units to fetch", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=config.max_workers) as pool:
        futures: list[Future] = [pool.submit(work, unit) for unit in units]
        for future in as_completed(futures):
            unit_id, error = future.result()
            with lock:
                done += 1
                if error:
                    errors += 1
                    append_jsonl(
                        config.state_dir / "errors.jsonl",
                        {
                            "dataset": dataset,
                            "unit": unit_id,
                            "error": error,
                            "at": datetime.now(UTC).isoformat(),
                        },
                    )
                now = time.monotonic()
                if done == total or now - last_report >= 5.0:
                    elapsed = now - started
                    rate = done / elapsed if elapsed else 0.0
                    remaining = total - done
                    eta = remaining / rate if rate else 0.0
                    print(
                        f"[{dataset}] {done:,}/{total:,} ({done / total:.1%}) "
                        f"elapsed {elapsed:,.0f}s rate {rate:.2f}/s ETA {eta:,.0f}s errors {errors}",
                        file=sys.stderr,
                    )
                    last_report = now
    return {"units": total, "errors": errors}


def run_download(config: Config) -> dict:
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    rate_limiter = RateLimiter(config.request_delay_seconds)
    client = BoeClient(
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
        rate_limiter=rate_limiter,
        user_agent=config.user_agent,
    )
    started = time.monotonic()
    catalog: list[dict] = []
    if config.include_legislacion:
        print("Fetching consolidated legislation catalog...", file=sys.stderr)
        catalog = fetch_catalog(client, config)
        if not catalog:
            catalog = layout.read_catalog(config.raw_dir)
    plan = build_plan(config, catalog)
    summary: dict[str, dict[str, int]] = {}
    total_units = sum(len(units) for units in plan.values())
    print(f"Plan: {total_units:,} units across {len(plan)} datasets", file=sys.stderr)
    for dataset, units in plan.items():
        summary[dataset] = _run_dataset(client, config, dataset, units)
    elapsed = time.monotonic() - started
    errors = sum(item["errors"] for item in summary.values())
    atomic_json(
        config.state_dir / "last_download.json",
        {
            "started_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "datasets": summary,
            "errors": errors,
        },
    )
    print(
        f"Download finished in {elapsed:,.0f}s; {errors} errors",
        file=sys.stderr,
    )
    return {"plan": {name: len(units) for name, units in plan.items()}, "errors": errors}
