from __future__ import annotations

import json
from dataclasses import replace
from itertools import pairwise

import pyarrow.parquet as pq
import pymupdf
import pytest

from boe_borme.archive import (
    expand_catalog,
    export_records,
    main,
    process_pending,
    recover_interrupted,
    save_response,
    status,
)
from boe_borme.archive_parse import chunks
from boe_borme.archive_store import ArchiveConfig, Store, digest, official_url
from boe_borme.client import Response


@pytest.fixture
def archive(tmp_path):
    config = ArchiveConfig(root=tmp_path, start_date="2024-01-01", end_date="2024-01-01",
                           include_legislation=False)
    store = Store(tmp_path)
    yield store, config
    store.close()


def add_document(store, url, kind="xml", document_id="BOE-A-2024-1"):
    store.document(document_id, "BOE", "2024-01-01", "Example", {}, "gazette", "test")
    store.enqueue(url, kind, 1, document_id)
    store.db.commit()


def test_recover_refuses_live_process(archive):
    import os
    store, config = archive
    lock = config.root / "run.lock"
    lock.write_text(str(os.getpid()))
    with pytest.raises(RuntimeError, match="still exists"):
        recover_interrupted(store)
    assert lock.exists()


def test_recover_marks_interrupted_run_without_deleting_data(archive):
    store, config = archive
    store.db.execute("INSERT INTO runs(id,status) VALUES('interrupted','running')")
    store.db.commit()
    recover_interrupted(store)
    assert store.db.execute("SELECT status FROM runs").fetchone()[0] == "paused_after_interruption"
    assert (config.root / "manifest.sqlite").exists()


def test_pause_request_and_export_guard(archive, tmp_path):
    _store, config = archive
    settings = tmp_path / "config.json"
    settings.write_text(json.dumps({"root": str(config.root),
                                   "start_date": "2024-01-01",
                                   "end_date": "2024-01-01"}))
    assert main(["pause", "--config", str(settings)]) == 0
    assert (config.root / "pause.request").exists()
    (config.root / "run.lock").write_text("123")
    with pytest.raises(RuntimeError, match="Cannot modify archive"):
        main(["export", "--config", str(settings)])


def test_idempotence_versions_and_current_view(archive):
    store, config = archive
    url = "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2024-1"
    add_document(store, url)
    first = b"<documento><texto><p>Original content.</p></texto></documento>"
    second = b"<documento><texto><p>Revised content.</p></texto></documento>"
    for content in (first, first, second):
        store.snapshot(url, content, {}, "test")
        process_pending(store, config, "test")
    assert store.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 2
    assert store.db.execute("SELECT COUNT(*) FROM records WHERE table_name='texts'").fetchone()[0] == 2
    rows = store.db.execute("SELECT payload_json FROM current_records WHERE table_name='texts'").fetchall()
    assert len(rows) == 1 and json.loads(rows[0][0])["text"] == "Revised content."
    assert export_records(store) > 0
    assert export_records(store) == 0
    path = next((config.root / "tables" / "texts").glob("*.parquet"))
    assert pq.read_table(path).num_rows == 2


def test_failed_documents_do_not_count_as_no_publication(archive):
    store, config = archive
    url = "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2024-1"
    add_document(store, url)
    row = store.db.execute("SELECT * FROM resources").fetchone()
    save_response(store, row, Response(404, b"", {}), "test")
    report = status(store, config, verify=True)
    assert report["resources"] == {"unavailable": 1}
    assert report["quality_status"] == "incomplete"
    assert report["documents_without_current_text"] == 1


def test_invalid_xml_does_not_partially_commit(archive):
    store, config = archive
    url = "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2024-1"
    add_document(store, url)
    store.snapshot(url, b"<documento><metadatos><titulo>Title</titulo></metadatos></documento>", {}, "test")
    process_pending(store, config, "test")
    assert store.db.execute("SELECT status FROM snapshots").fetchone()[0] == "error"
    assert store.db.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0


def test_reference_text_is_not_document_body(archive):
    store, config = archive
    url = "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2024-1"
    add_document(store, url)
    content = b"<documento><analisis><referencias><texto>Related title.</texto></referencias></analisis><texto><p>Real body.</p></texto></documento>"
    store.snapshot(url, content, {}, "test")
    process_pending(store, config, "test")
    texts = store.db.execute("SELECT payload_json FROM records WHERE table_name='texts'").fetchall()
    assert len(texts) == 1 and json.loads(texts[0][0])["text"] == "Real body."
    assert store.db.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0


def test_rag_covers_every_character():
    text = "Paragraph.\n" * 700
    fragments = list(chunks(text, 400, 40))
    assert fragments[0][0] == 0 and fragments[-1][1] == len(text)
    for start, end, value in fragments:
        assert value == text[start:end]
    assert all(b[0] <= a[1] for a, b in pairwise(fragments))


def test_borme_acts_and_evidence(archive):
    store, config = archive
    url = "https://www.boe.es/diario_borme/xml.php?id=BORME-A-2024-1-28"
    add_document(store, url, document_id="BORME-A-2024-1-28")
    content = b'<documento><texto><p class="articulo">1 - COMPANY SL.</p><p>Nombramientos. Adm: PERSON. Datos registrales. T 1, F 2.</p><p class="articulo">2 - OTHER SL.</p><p>Capital: 3000 Euros.</p></texto></documento>'
    store.snapshot(url, content, {}, "test")
    process_pending(store, config, "test")
    acts = store.db.execute("SELECT payload_json FROM records WHERE table_name='borme_acts'").fetchall()
    assert len(acts) == 2
    for row in acts:
        payload = json.loads(row[0])
        for field in payload["fields"]:
            assert payload["text"][field["start"]:field["end"]] == field["raw_value"]


def test_pdf_page_coverage(archive):
    store, config = archive
    url = "https://www.boe.es/example.pdf"
    add_document(store, url, "pdf")
    with pymupdf.open() as pdf:
        for number in range(2):
            page = pdf.new_page()
            page.insert_text((50, 50), f"Page {number + 1}: " + "Full native content. " * 8)
        content = pdf.tobytes()
    store.snapshot(url, content, {}, "test")
    process_pending(store, config, "test")
    assert store.db.execute("SELECT COUNT(*) FROM records WHERE table_name='pages'").fetchone()[0] == 2
    assert store.db.execute("SELECT status FROM snapshots").fetchone()[0] == "processed"


def test_corrupt_object_fails_integrity(archive):
    store, config = archive
    url = "https://www.boe.es/example.pdf"
    add_document(store, url, "pdf")
    checksum = store.snapshot(url, b"%PDF-test", {}, "test")
    (store.root / "objects" / checksum[:2] / checksum).write_bytes(b"corrupt")
    assert status(store, config, verify=True)["integrity_errors"]


def test_catalogue_revision_schedules_all_norm_resources(archive):
    store, _ = archive
    url = "https://www.boe.es/datosabiertos/api/legislacion-consolidada?limit=10000&offset=0"
    snapshot = {"url": url, "sha256": "test"}
    expand_catalog(store, snapshot, json.dumps({"data": [{"identificador": "BOE-A-2024-1", "fecha_actualizacion": "v1"}]}).encode(), "test")
    store.db.execute("UPDATE resources SET status='downloaded'")
    expand_catalog(store, snapshot, json.dumps({"data": [{"identificador": "BOE-A-2024-1", "fecha_actualizacion": "v2"}]}).encode(), "test")
    assert store.db.execute("SELECT COUNT(*) FROM resources WHERE status='pending'").fetchone()[0] == 5


def test_limits_and_official_urls(archive):
    _, config = archive
    assert official_url("https://evil.example/file.pdf") is None
    assert official_url("https://www.boe.es/file.pdf#page=1") == "https://www.boe.es/file.pdf"
    assert digest("a") != digest("b")
    assert replace(config, end_date=None).end
