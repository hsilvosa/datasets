"""Download representative XML, HTML, PDF and legislative resources before a backfill."""
from __future__ import annotations

import json

from boe_borme.archive import export_records, fetch, process_pending, save_response, status
from boe_borme.archive_store import ArchiveConfig, Store
from boe_borme.client import BoeClient, RateLimiter


def main():
    config = ArchiveConfig.load("configs/archive-smoke.json")
    store = Store(config.root)
    client = BoeClient(timeout=60, max_retries=2, rate_limiter=RateLimiter(0.3))
    doc_ids = ["BOE-A-2024-1", "BORME-A-2024-10-28", "BORME-C-2024-117"]
    for doc_id in doc_ids:
        publication = "BORME" if doc_id.startswith("BORME") else "BOE"
        date8 = "20240101" if publication == "BOE" else "20240115"
        day = f"{date8[:4]}-{date8[4:6]}-{date8[6:]}"
        store.document(doc_id, publication, day, doc_id, {}, "gazette", "sample")
        prefix = "diario_borme" if publication == "BORME" else "diario_boe"
        for endpoint, kind in (("xml", "xml"), ("txt", "html")):
            store.enqueue(f"https://www.boe.es/{prefix}/{endpoint}.php?id={doc_id}",
                          kind, 1, doc_id)
        pdf_url = f"https://www.boe.es/{publication.lower()}/dias/{day.replace('-', '/')}/pdfs/{doc_id}.pdf"
        store.enqueue(pdf_url, "pdf", 1, doc_id)
    norm_id = "BOE-A-1978-31229"
    store.document(f"LC:{norm_id}", "BOE", "1978-12-29", "Constitution", {}, "legislation", "sample")
    for endpoint, kind in (("texto", "xml"), ("metadatos", "metadata_json"),
                           ("metadata-eli", "metadata_xml"), ("analisis", "analysis_json"),
                           ("texto/indice", "index_json")):
        store.enqueue(f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{norm_id}/{endpoint}",
                      kind, 1, f"LC:{norm_id}")
    store.db.commit()
    urls = [row[0] for row in store.db.execute("SELECT url FROM links WHERE document_id IN (?,?,?,?)",
                                             (*doc_ids, f"LC:{norm_id}"))]
    for url in dict.fromkeys(urls):
        row = store.db.execute("SELECT * FROM resources WHERE url=?", (url,)).fetchone()
        if row["status"] == "pending":
            response, _ = fetch(client, row)
            save_response(store, row, response, "sample")
        while process_pending(store, config, "sample", 16):
            pass
    export_records(store)
    print(json.dumps(status(store, config, verify=True), ensure_ascii=False, indent=2))
    store.close()


if __name__ == "__main__":
    main()
