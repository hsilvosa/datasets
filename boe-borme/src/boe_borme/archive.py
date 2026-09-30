"""Complete gazette archive: discover, fetch, extract, export, and audit."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote

import pyarrow as pa
import pyarrow.parquet as pq

from .archive_parse import PARSER_VERSION, Extractor, resource_kind
from .archive_store import ArchiveConfig, Store, digest, json_text, utcnow
from .client import BoeClient, RateLimiter, Response
from .io_utils import atomic_json
from .parser import parse_sumario, xml_payload, xml_status_code

BASE = "https://www.boe.es"


def recover_interrupted(store: Store) -> None:
    """Recover only after positively checking that the lock owner has exited."""
    lock = store.root / "run.lock"
    if lock.exists():
        pid = int(lock.read_text().strip())
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            handle = kernel.OpenProcess(0x1000, False, pid)
            if handle:
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel.CloseHandle(handle)
                raise RuntimeError(f"PID {pid} still exists; refusing recovery")
            if ctypes.get_last_error() != 87:
                raise RuntimeError("Cannot verify the lock owner; refusing recovery")
        else:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError(f"PID {pid} still exists; refusing recovery")
        lock.unlink()
    store.db.execute("UPDATE runs SET status='paused_after_interruption',finished_at=? "
                     "WHERE status='running'", (utcnow(),))
    store.db.commit()


def days(start: str, end: str):
    current = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    while current <= stop:
        yield current
        current += timedelta(days=1)


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def seed(store: Store, config: ArchiveConfig, run_id: str) -> None:
    for publication in ("BOE", "BORME"):
        for day in days(config.start_date, config.end):
            date8 = day.strftime("%Y%m%d")
            url = store.enqueue(f"{BASE}/datosabiertos/api/{publication.lower()}/sumario/{date8}",
                                "sumario", 0)
            existing = store.db.execute("SELECT status,sha256 FROM resources WHERE url=?", (url,)).fetchone()
            if existing["status"] != "pending" or existing["sha256"] or not config.legacy_raw:
                continue
            legacy = config.legacy_raw / f"{publication.lower()}_sumario" / date8[:4] / f"{date8}.json"
            if legacy.exists():
                content = legacy.read_bytes()
                payload = json.loads(content)
                if str(payload.get("status", {}).get("code")) == "200":
                    stamp = datetime.fromtimestamp(legacy.stat().st_mtime, tz=UTC).isoformat()
                    store.snapshot(url, content, {"imported_from": str(legacy)}, run_id, stamp)
        store.db.commit()
    if config.include_legislation:
        store.enqueue(f"{BASE}/datosabiertos/api/legislacion-consolidada?limit=10000&offset=0",
                      "catalog_json", 1)
        from .layout import AUX_TABLES
        for name in AUX_TABLES:
            store.enqueue(f"{BASE}/datosabiertos/api/datos-auxiliares/{name}", "aux_json", 5)
    store.db.commit()


def expand_sumario(store: Store, snapshot, content: bytes, run_id: str) -> None:
    url = snapshot["url"]
    publication = "BORME" if "/borme/" in url else "BOE"
    payload = json.loads(content) if content.lstrip().startswith(b"{") else xml_payload(content)
    parsed = parse_sumario(payload, publication)
    expected = datetime.strptime(url.rsplit("/", 1)[1], "%Y%m%d").replace(tzinfo=UTC).date()
    if parsed["publication_date"] != expected:
        raise ValueError("Sumario publication date mismatch")
    for index, issue in enumerate(parsed["issues"]):
        doc_id = issue.get("issue_id") or f"{publication}:issue:{expected}:{index}"
        store.document(doc_id, publication, str(expected), doc_id, issue, "issue", run_id)
        store.record("issues", doc_id, url, snapshot["sha256"], PARSER_VERSION,
                     str(index), issue)
        if issue.get("issue_url_pdf"):
            store.enqueue(issue["issue_url_pdf"], "pdf", 35, doc_id, "issue_pdf")
        else:
            store.issue(doc_id, url, "issue_pdf_missing", "No issue PDF URL in sumario")
    for document in parsed["documents"]:
        doc_id = document.get("document_id")
        if not doc_id:
            raise ValueError("Sumario contains a document with no identifier")
        store.document(doc_id, publication, str(expected), document.get("titulo"),
                       document, "gazette", run_id)
        store.record("documents", doc_id, url, snapshot["sha256"], PARSER_VERSION,
                     doc_id, document)
        found = False
        for key, kind, priority in (("url_xml", "xml", 10), ("url_pdf", "pdf", 30),
                                    ("url_html", "html", 40)):
            if document.get(key):
                found = True
                store.enqueue(document[key], kind, priority, doc_id, key)
        if not found:
            store.issue(doc_id, url, "document_without_url", "No document resource advertised")
    # Capture extra files advertised by the source, not just fields in SUMARIO_SCHEMA.
    for node in walk(payload):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.startswith("url_"):
                    value = value.get("texto") if isinstance(value, dict) else value
                    if isinstance(value, str) and value.startswith("http"):
                        store.enqueue(value, resource_kind(value), 40)
    store.record("source_payloads", f"{publication}:sumario:{expected}", url,
                 snapshot["sha256"], PARSER_VERSION, "payload", payload)


def expand_catalog(store: Store, snapshot, content: bytes, run_id: str,
                   config: ArchiveConfig | None = None) -> None:
    payload = json.loads(content)
    items = payload.get("data")
    if not isinstance(items, list):
        raise TypeError("Invalid legislation catalogue")
    if len(items) == 10000:
        offset = int(snapshot["url"].rsplit("offset=", 1)[1]) + 10000
        store.enqueue(f"{BASE}/datosabiertos/api/legislacion-consolidada?limit=10000&offset={offset}",
                      "catalog_json", 1)
    for item in items:
        norm_id = item.get("identificador")
        if not norm_id:
            raise ValueError("Catalogue entry missing identifier")
        compact = str(item.get("fecha_publicacion", ""))
        day = f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}" if len(compact) == 8 else None
        prior = store.db.execute("SELECT metadata_json FROM documents WHERE id=?", (f"LC:{norm_id}",)).fetchone()
        changed = prior and json.loads(prior[0]).get("fecha_actualizacion") != item.get("fecha_actualizacion")
        store.document(f"LC:{norm_id}", "BOE", day, item.get("titulo"), item,
                       "legislation", run_id)
        store.record("legislation_catalog", f"LC:{norm_id}", snapshot["url"],
                     snapshot["sha256"], PARSER_VERSION, norm_id, item)
        for endpoint, kind, priority in (("metadatos", "metadata_json", 60),
                                         ("metadata-eli", "metadata_xml", 60),
                                         ("analisis", "analysis_json", 60),
                                         ("texto", "xml", 55),
                                         ("texto/indice", "index_json", 65)):
            store.enqueue(f"{BASE}/datosabiertos/api/legislacion-consolidada/id/{norm_id}/{endpoint}",
                          kind, priority, f"LC:{norm_id}", endpoint)
        if changed:
            store.db.execute("UPDATE resources SET status='pending' WHERE url IN "
                             "(SELECT url FROM links WHERE document_id=?)", (f"LC:{norm_id}",))
        if config and config.legacy_raw and not changed:
            legacy_metadata = config.legacy_raw / "boe_legislacion" / norm_id / "metadata.json"
            if legacy_metadata.exists():
                cached = json.loads(legacy_metadata.read_text(encoding="utf-8"))
                if cached.get("fecha_actualizacion") == item.get("fecha_actualizacion"):
                    for endpoint, path in (
                        ("analisis", legacy_metadata.parent / "analisis.json"),
                        ("texto", config.legacy_raw / "boe_legislacion_texto" / norm_id / "texto.xml"),
                    ):
                        url = f"{BASE}/datosabiertos/api/legislacion-consolidada/id/{norm_id}/{endpoint}"
                        existing = store.db.execute("SELECT sha256 FROM resources WHERE url=?", (url,)).fetchone()
                        if path.exists() and not existing[0]:
                            stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
                            store.snapshot(url, path.read_bytes(), {"imported_from": str(path)}, run_id, stamp)


def expand_index(store: Store, snapshot, payload: dict) -> None:
    links = store.db.execute("SELECT document_id FROM links WHERE url=?", (snapshot["url"],)).fetchall()
    base = snapshot["url"].removesuffix("/indice")
    parent = store.db.execute("SELECT s.* FROM snapshots s JOIN resources r ON s.url=r.url "
                              "AND s.sha256=r.sha256 WHERE s.url=? AND s.status='processed'",
                              (base,)).fetchone()
    available = {}
    if parent:
        tree = ET.fromstring((store.root / parent["path"]).read_bytes())
        available = {node.get("id"): node for node in tree.findall(".//bloque")}
    ids = set()
    for node in walk(payload.get("data")):
        if isinstance(node, dict):
            block_id = node.get("id") or node.get("id_bloque")
            if isinstance(block_id, str):
                ids.add(block_id)
    for block_id in ids:
        for link in links:
            if block_id in available:
                # The complete source XML already contains every version of this block.
                # Register its advertised endpoint and exact serialized content without
                # spending a second HTTP request on the same text.
                node = available[block_id]
                store.record("indexed_blocks", link["document_id"], base, parent["sha256"],
                             PARSER_VERSION, block_id, {
                                 "block_id": block_id,
                                 "advertised_url": f"{base}/bloque/{quote(block_id, safe='')}",
                                 "source_container_url": base,
                                 "xml": ET.tostring(node, encoding="unicode"),
                                 "version_count": len(node.findall("version")),
                             })
            else:
                store.enqueue(f"{base}/bloque/{quote(block_id, safe='')}", "block_xml", 70,
                              link["document_id"], "consolidated_block")
    if not ids:
        for link in links:
            store.issue(link["document_id"], snapshot["url"], "block_index_review",
                        "No block identifiers recognized in source index")


def process_snapshot(store: Store, config: ArchiveConfig, snapshot, run_id: str) -> None:
    content = (store.root / snapshot["path"]).read_bytes()
    if digest(content) != snapshot["sha256"]:
        raise ValueError("Source checksum mismatch")
    resource = store.db.execute("SELECT kind FROM resources WHERE url=?", (snapshot["url"],)).fetchone()
    kind = resource["kind"]
    if kind == "asset":
        if content.lstrip().startswith(b"%PDF-"):
            kind = "pdf"
        elif content.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"II*\x00", b"MM\x00*")):
            kind = "image"
    if kind == "sumario":
        expand_sumario(store, snapshot, content, run_id)
        return
    if kind == "catalog_json":
        expand_catalog(store, snapshot, content, run_id, config)
        return
    if kind.endswith("_json") or kind == "metadata_xml":
        payload = json.loads(content) if content.lstrip().startswith(b"{") else xml_payload(content)
        if kind == "index_json":
            expand_index(store, snapshot, payload)
        links = store.db.execute("SELECT DISTINCT document_id FROM links WHERE url=?", (snapshot["url"],)).fetchall()
        for link in links or [{"document_id": "AUX:" + snapshot["url"].rsplit("/", 1)[-1]}]:
            store.record("metadata", link["document_id"], snapshot["url"], snapshot["sha256"],
                         PARSER_VERSION, "payload", {"kind": kind, "value": payload})
        return
    links = store.db.execute("SELECT DISTINCT document_id FROM links WHERE url=?", (snapshot["url"],)).fetchall()
    for link in links or [{"document_id": "RESOURCE:" + digest(snapshot["url"])}]:
        extractor = Extractor(store, config, link["document_id"], snapshot["url"], snapshot["sha256"])
        if kind in ("xml", "block_xml"):
            if kind == "block_xml":
                root = ET.fromstring(content)
                if root.find(".//texto") is None:
                    wrapper = ET.Element("texto")
                    for block in root.findall(".//bloque"):
                        wrapper.append(block)
                    content = ET.tostring(wrapper, encoding="utf-8")
            extractor.xml(content)
        elif kind == "html":
            extractor.html(content)
        elif kind == "pdf":
            extractor.pdf(content)
        elif kind == "image":
            extractor.image(content)
        else:
            extractor.asset(content, kind)


def process_pending(store: Store, config: ArchiveConfig, run_id: str, limit: int = 32) -> int:
    rows = store.db.execute("SELECT s.* FROM snapshots s JOIN resources r ON s.url=r.url "
                            "WHERE s.status='pending' ORDER BY r.priority,s.id LIMIT ?", (limit,)).fetchall()
    for snapshot in rows:
        try:
            store.db.execute("SAVEPOINT extraction")
            process_snapshot(store, config, snapshot, run_id)
            store.db.execute("UPDATE snapshots SET status='processed',error=NULL WHERE id=?", (snapshot["id"],))
            store.db.execute("RELEASE extraction")
        except Exception as exc:  # noqa: BLE001 - failures are persistent retryable work
            store.db.execute("ROLLBACK TO extraction")
            store.db.execute("RELEASE extraction")
            store.db.execute("UPDATE snapshots SET status='error',error=? WHERE id=?", (str(exc), snapshot["id"]))
            print(f"Extraction error: {snapshot['url']}: {exc}", file=sys.stderr, flush=True)
        store.db.commit()
    return len(rows)


def accept_for(kind: str) -> str:
    if kind in ("xml", "block_xml", "metadata_xml"):
        return "application/xml"
    if kind == "html":
        return "text/html"
    if kind == "pdf":
        return "application/pdf"
    return "application/json" if kind.endswith("_json") or kind == "sumario" else "*/*"


def fetch(client: BoeClient, row) -> tuple[Response, str | None]:
    try:
        response = client.get(row["url"], accept=accept_for(row["kind"]),
                              if_none_match=row["etag"], if_modified_since=row["last_modified"])
    except RuntimeError:
        if row["kind"] != "sumario":
            raise
        response = client.get(row["url"], accept="application/xml")
        if response.status != 200 or xml_status_code(response.content) != "200":
            raise ValueError("Both sumario representations failed; day remains pending") from None
        return response, None
    if row["kind"] == "sumario" and response.status == 200:
        try:
            payload = json.loads(response.content)
            code = str(payload.get("status", {}).get("code"))
        except (ValueError, AttributeError):
            code = ""
        if code != "200":
            xml = client.get(row["url"], accept="application/xml")
            if xml.status == 200 and xml_status_code(xml.content) == "200":
                return xml, None
            raise ValueError("Unsuccessful sumario response; not classified as empty")
    if response.status not in (200, 304, 404):
        raise ValueError(f"Unexpected HTTP {response.status}")
    if response.status == 200:
        if not response.content:
            raise ValueError("Empty HTTP 200 response")
        if row["kind"] == "pdf" and not response.content.lstrip().startswith(b"%PDF-"):
            raise ValueError("PDF endpoint returned non-PDF data")
        if row["kind"].endswith("_json"):
            data = json.loads(response.content)
            if "status" in data and str(data["status"].get("code")) != "200":
                raise ValueError("API returned an unsuccessful envelope")
        if row["kind"] in ("xml", "block_xml", "metadata_xml"):
            root = ET.fromstring(response.content)
            status = root.find("./status/code")
            if status is not None and status.text != "200":
                raise ValueError("XML endpoint returned an unsuccessful envelope")
    return response, None


def save_response(store: Store, row, response: Response, run_id: str) -> None:
    url = row["url"]
    if response.status == 200:
        store.snapshot(url, response.content, response.headers, run_id)
    else:
        stamp = utcnow()
        if response.status == 304:
            if not row["sha256"]:
                raise ValueError("HTTP 304 without archived content")
            store.db.execute("UPDATE resources SET status='downloaded',checked_at=?,error=NULL WHERE url=?", (stamp, url))
        else:
            # Only a sumario 404 means there was no edition. A document 404 remains a gap.
            status = "no_publication" if row["kind"] == "sumario" else "unavailable"
            store.db.execute("UPDATE resources SET status=?,checked_at=?,error=? WHERE url=?",
                             (status, stamp, "HTTP 404", url))
        store.db.execute("INSERT INTO observations(url,sha256,http_status,observed_at,run_id,headers_json) VALUES(?,?,?,?,?,?)",
                         (url, row["sha256"], response.status, stamp, run_id, json_text(response.headers)))
    store.db.commit()


def export_records(store: Store, batch_size: int = 2000) -> int:
    schema = pa.schema([("record_id", pa.string()), ("document_id", pa.string()),
                        ("publication", pa.string()), ("year", pa.int32()),
                        ("source_url", pa.string()), ("source_sha256", pa.string()),
                        ("retrieved_at_utc", pa.string()), ("run_id", pa.string()),
                        ("parser_version", pa.string()), ("text", pa.large_string()),
                        ("payload_json", pa.large_string())])
    written = 0
    for table in store.db.execute("SELECT DISTINCT table_name FROM records").fetchall():
        name = table[0]
        last = store.db.execute("SELECT MAX(last_seq) FROM exports WHERE table_name=?", (name,)).fetchone()[0] or 0
        while True:
            rows = store.db.execute("SELECT r.*,s.retrieved_at,s.run_id FROM records r LEFT JOIN "
                                    "snapshots s ON r.source_url=s.url AND r.source_sha256=s.sha256 "
                                    "WHERE table_name=? AND seq>? ORDER BY seq LIMIT ?",
                                    (name, last, batch_size)).fetchall()
            if not rows:
                break
            filename = f"tables/{name}/part-{rows[0]['seq']:012d}-{rows[-1]['seq']:012d}.parquet"
            target = store.root / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            values = [{"record_id": row["key"], "document_id": row["document_id"],
                       "publication": row["publication"], "year": row["year"],
                       "source_url": row["source_url"], "source_sha256": row["source_sha256"],
                       "retrieved_at_utc": row["retrieved_at"], "run_id": row["run_id"],
                       "parser_version": row["parser_version"],
                       "text": json.loads(row["payload_json"]).get("text"),
                       "payload_json": row["payload_json"]} for row in rows]
            temporary = target.with_suffix(".parquet.tmp")
            pq.write_table(pa.Table.from_pylist(values, schema=schema), temporary, compression="zstd")
            temporary.replace(target)
            last = rows[-1]["seq"]
            store.db.execute("INSERT OR REPLACE INTO exports VALUES(?,?,?,?)",
                             (filename, name, last, digest(target.read_bytes())))
            store.db.commit()
            written += 1
    return written


def status(store: Store, config: ArchiveConfig, verify: bool = False) -> dict:
    counts = lambda sql: {row[0]: row[1] for row in store.db.execute(sql)}
    resources = counts("SELECT status,COUNT(*) FROM resources GROUP BY status")
    extraction = counts("SELECT status,COUNT(*) FROM snapshots GROUP BY status")
    documents = counts("SELECT category,COUNT(*) FROM documents GROUP BY category")
    records = counts("SELECT table_name,COUNT(*) FROM records GROUP BY table_name")
    issues = counts("SELECT category,COUNT(*) FROM issues WHERE resolved=0 GROUP BY category")
    missing_days = 0
    for publication in ("boe", "borme"):
        for day in days(config.start_date, config.end):
            url = f"{BASE}/datosabiertos/api/{publication}/sumario/{day:%Y%m%d}"
            row = store.db.execute("SELECT status FROM resources WHERE url=?", (url,)).fetchone()
            if row is None or row[0] not in ("downloaded", "no_publication"):
                missing_days += 1
    without_text = store.db.execute("SELECT COUNT(*) FROM documents d WHERE NOT EXISTS "
                                   "(SELECT 1 FROM records r JOIN resources q ON r.source_url=q.url "
                                   "AND r.source_sha256=q.sha256 WHERE r.document_id=d.id "
                                   "AND r.table_name='texts')").fetchone()[0]
    run = store.db.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
    gaps = (missing_days + without_text + resources.get("pending", 0) + resources.get("error", 0)
            + resources.get("unavailable", 0) + extraction.get("pending", 0)
            + extraction.get("error", 0) + sum(issues.values()))
    integrity_errors = []
    if verify:
        for row in store.db.execute("SELECT DISTINCT sha256,path FROM snapshots"):
            path = store.root / row["path"]
            if not path.exists() or digest(path.read_bytes()) != row["sha256"]:
                integrity_errors.append(str(path))
        for row in store.db.execute("SELECT filename,sha256 FROM exports"):
            path = store.root / row["filename"]
            if not path.exists() or digest(path.read_bytes()) != row["sha256"]:
                integrity_errors.append(str(path))
    result = {"generated_at": utcnow(), "start_date": config.start_date,
              "end_date": config.end, "run": dict(run) if run else None,
              "resources": resources, "extraction": extraction, "documents": documents,
              "records": records, "unresolved_issues": issues,
              "missing_sumario_days": missing_days, "documents_without_current_text": without_text,
              "archived_bytes": store.db.execute("SELECT COALESCE(SUM(size_bytes),0) FROM snapshots").fetchone()[0],
              "integrity_errors": integrity_errors,
              "quality_status": "pass" if not gaps and verify and not integrity_errors else "incomplete",
              "integrity_verified": verify,
              "remaining_work": gaps,
              "scope": "Public BOE/BORME gazette resources advertised by source; complete consolidated catalogue"}
    atomic_json(store.root / "artifacts" / "progress.json", result)
    return result


def run(config: ArchiveConfig, max_requests: int | None = None) -> dict:
    store = Store(config.root)
    lock_path = config.root / "run.lock"
    try:
        lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        store.close()
        raise RuntimeError(f"Archive already locked: {lock_path}. Check the running PID before recovery.") from None
    os.write(lock, str(os.getpid()).encode())
    os.close(lock)
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{os.getpid()}"
    request_count = 0
    client = BoeClient(timeout=config.timeout_seconds, max_retries=config.max_retries,
                       rate_limiter=RateLimiter(config.request_delay_seconds))
    store.db.execute("INSERT INTO runs(id,started_at,status,config_json) VALUES(?,?,'running',?)",
                     (run_id, utcnow(), json_text(config.__dict__)))
    store.db.commit()
    try:
        (config.root / "pause.request").unlink(missing_ok=True)
        previous_parser = store.db.execute("SELECT value FROM settings WHERE key='parser_version'").fetchone()
        if not previous_parser or previous_parser[0] != PARSER_VERSION:
            store.db.execute("UPDATE snapshots SET status='pending',error=NULL")
        store.db.execute("INSERT OR REPLACE INTO settings VALUES('parser_version',?)", (PARSER_VERSION,))
        # Failed work is retried on the next execution, never counted as a publication-free day.
        store.db.execute("UPDATE resources SET status='pending' WHERE status IN ('error','unavailable')")
        store.db.execute("UPDATE snapshots SET status='pending',error=NULL WHERE status='error'")
        cutoff = (datetime.now(UTC) - timedelta(days=config.recheck_after_days)).isoformat()
        store.db.execute("UPDATE resources SET status='pending' WHERE checked_at<?", (cutoff,))
        recent = (date.fromisoformat(config.end) - timedelta(days=config.refresh_days)).strftime("%Y%m%d")
        store.db.execute("UPDATE resources SET status='pending' WHERE kind='sumario' AND substr(url,-8)>?", (recent,))
        # Always refresh the catalogue so revised norms and new entries are discovered.
        store.db.execute("UPDATE resources SET status='pending' WHERE kind IN ('catalog_json','aux_json')")
        store.db.commit()
        seed(store, config, run_id)
        print(json.dumps({"event": "started", "run_id": run_id,
                          "start_date": config.start_date, "end_date": config.end,
                          "resources": status(store, config)["resources"]}), flush=True)
        last_report = time.monotonic()
        last_export = time.monotonic()
        with ThreadPoolExecutor(max_workers=config.max_workers) as pool:
            while True:
                if (config.root / "pause.request").exists():
                    break
                processed = process_pending(store, config, run_id, 16)
                if max_requests is not None and request_count >= max_requests:
                    break
                limit = min(config.max_workers * 4, (max_requests - request_count)
                            if max_requests is not None else config.max_workers * 4)
                pending = store.db.execute("SELECT * FROM resources WHERE status='pending' ORDER BY priority,url LIMIT ?", (limit,)).fetchall()
                if not pending:
                    if processed:
                        continue
                    break
                futures = {pool.submit(fetch, client, row): row for row in pending}
                for future in as_completed(futures):
                    row = futures[future]
                    request_count += 1
                    try:
                        response, _ = future.result()
                        save_response(store, row, response, run_id)
                    except Exception as exc:  # noqa: BLE001 - preserve failed resource for retry
                        store.db.execute("UPDATE resources SET status='error',attempts=attempts+1,error=?,checked_at=? WHERE url=?",
                                         (str(exc), utcnow(), row["url"]))
                        store.db.commit()
                        print(f"Download error: {row['url']}: {exc}", file=sys.stderr, flush=True)
                now = time.monotonic()
                if now - last_report > 30:
                    report = status(store, config)
                    print(json.dumps({"at": report["generated_at"], "resources": report["resources"],
                                      "documents": report["documents"], "extraction": report["extraction"],
                                      "requests_this_run": request_count}, ensure_ascii=False), flush=True)
                    last_report = now
                if now - last_export > 180:
                    export_records(store)
                    last_export = now
        export_records(store)
        paused = (config.root / "pause.request").exists()
        report = status(store, config, verify=max_requests is None and not paused)
        final_status = "complete" if report["quality_status"] == "pass" else "needs_attention"
        if max_requests is not None:
            final_status = "paused_at_request_limit"
        if paused:
            final_status = "paused_by_user"
        store.db.execute("UPDATE runs SET status=?,finished_at=? WHERE id=?", (final_status, utcnow(), run_id))
        store.db.commit()
        return status(store, config, verify=max_requests is None and not paused)
    except BaseException as exc:
        store.db.execute("UPDATE runs SET status='failed',finished_at=?,error=? WHERE id=?",
                         (utcnow(), str(exc), run_id))
        store.db.commit()
        status(store, config)
        raise
    finally:
        lock_path.unlink(missing_ok=True)
        store.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "audit", "export", "retry", "pause", "recover"))
    parser.add_argument("--config", default="configs/archive-pilot.json")
    parser.add_argument("--max-requests", type=int)
    args = parser.parse_args(argv)
    config = ArchiveConfig.load(args.config)
    if args.max_requests is not None and args.max_requests < 1:
        parser.error("--max-requests must be positive")
    if args.command == "run":
        output = run(config, args.max_requests)
    else:
        if args.command == "pause":
            config.root.mkdir(parents=True, exist_ok=True)
            (config.root / "pause.request").write_text(utcnow(), encoding="utf-8")
        if args.command in ("export", "retry") and (config.root / "run.lock").exists():
            raise RuntimeError("Cannot modify archive while the runner is active or unrecovered")
        store = Store(config.root)
        try:
            if args.command == "recover":
                recover_interrupted(store)
            if args.command == "export":
                export_records(store)
            if args.command == "retry":
                if (config.root / "run.lock").exists():
                    raise RuntimeError("Cannot reset work while the runner is active")
                store.db.execute("UPDATE resources SET status='pending' WHERE status IN ('error','unavailable')")
                store.db.execute("UPDATE snapshots SET status='pending' WHERE status='error'")
                store.db.commit()
            output = status(store, config, verify=args.command == "audit")
        finally:
            store.close()
    print(json.dumps(output, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - CLI reports failure with its full traceback
        traceback.print_exc()
        raise SystemExit(1)
