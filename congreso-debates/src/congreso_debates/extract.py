from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .client import CongresoClient
from .config import Config

logger = logging.getLogger(__name__)


def extract(config: Config) -> dict[str, Any]:
    """Discover and download all voting files, speech catalogs, and all Diario de Sesiones PDFs."""
    client = CongresoClient(
        user_agent=config.user_agent,
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
        delay=config.request_delay_seconds,
    )

    config.raw_dir.mkdir(parents=True, exist_ok=True)
    intervenciones_raw_dir = config.raw_dir / "intervenciones"
    intervenciones_raw_dir.mkdir(parents=True, exist_ok=True)
    pdf_raw_dir = config.raw_dir / "diarios_pdf"
    pdf_raw_dir.mkdir(parents=True, exist_ok=True)

    total_downloaded = 0
    total_skipped = 0
    total_failed = 0
    legs_summary = {}

    # 1. Extract all voting files per legislature
    for leg in config.legislatures:
        leg_dir = config.raw_dir / f"L{leg}"
        leg_dir.mkdir(parents=True, exist_ok=True)

        urls = client.discover_voting_json_urls(leg)
        if config.max_sessions_per_leg and len(urls) > config.max_sessions_per_leg:
            urls = urls[: config.max_sessions_per_leg]

        def _fetch_one_vote(url: str) -> tuple[str, bool, bool]:
            m = re.search(r"(Sesion\d+_[^/]+_Votacion\d+)", url.replace("/", "_"))
            fname = m.group(1) if m else Path(url).name
            if not fname.endswith(".json"):
                fname += ".json"

            dest_file = leg_dir / fname
            if dest_file.exists() and dest_file.stat().st_size > 0:
                return fname, False, True

            data = client.fetch_json(url)
            if data:
                dest_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                return fname, True, False
            return fname, False, False

        leg_dl = 0
        leg_sk = 0
        leg_fl = 0

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_fetch_one_vote, u) for u in urls]
            for f in as_completed(futures):
                fname, dl, sk = f.result()
                if dl:
                    leg_dl += 1
                elif sk:
                    leg_sk += 1
                else:
                    leg_fl += 1

        total_downloaded += leg_dl
        total_skipped += leg_sk
        total_failed += leg_fl
        legs_summary[f"L{leg}"] = {"downloaded": leg_dl, "skipped": leg_sk, "failed": leg_fl, "total": len(urls)}
        logger.info("L%d voting files: %d downloaded, %d skipped, %d total", leg, leg_dl, leg_sk, len(urls))

    # 2. Extract speech / interventions catalog
    intervenciones_downloaded = 0
    intervenciones_urls = client.discover_intervenciones_urls()
    for url in intervenciones_urls:
        fname = Path(url).name
        dest_file = intervenciones_raw_dir / fname
        if dest_file.exists() and dest_file.stat().st_size > 0:
            intervenciones_downloaded += 1
            continue
        data = client.fetch_json(url)
        if data:
            dest_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            intervenciones_downloaded += 1

    # 3. Extract ALL official Diario de Sesiones PDFs for verbatim speech texts (fast parallel download)
    pdf_downloaded = 0
    pdf_skipped = 0
    if config.download_speech_pdfs:
        pdf_urls = set()
        for jf in intervenciones_raw_dir.glob("*.json"):
            try:
                items = json.loads(jf.read_text(encoding="utf-8"))
                for it in items:
                    p = it.get("ENLACEPDF")
                    if p and ".PDF" in p.upper():
                        clean_url = p.split("#")[0]
                        if clean_url.endswith(".PDF") or clean_url.endswith(".pdf"):
                            pdf_urls.add(clean_url)
            except Exception:
                pass

        target_pdf_urls = sorted(list(pdf_urls))
        if config.max_speech_pdfs:
            target_pdf_urls = target_pdf_urls[: config.max_speech_pdfs]

        logger.info("Starting parallel download of all %d Diario de Sesiones PDFs...", len(target_pdf_urls))

        def _fetch_one_pdf(url: str) -> tuple[str, bool, bool]:
            fname = Path(url).name
            dest = pdf_raw_dir / fname
            if dest.exists() and dest.stat().st_size > 1000:
                return fname, False, True
            ok = client.download_pdf(url, dest)
            return fname, ok, False

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(_fetch_one_pdf, u) for u in target_pdf_urls]
            for f in as_completed(futures):
                fname, downloaded, skipped = f.result()
                if downloaded:
                    pdf_downloaded += 1
                    if pdf_downloaded % 50 == 0:
                        logger.info("Downloaded %d / %d PDFs...", pdf_downloaded, len(target_pdf_urls))
                elif skipped:
                    pdf_skipped += 1

        logger.info("PDF downloads summary: %d downloaded, %d skipped, total %d available", pdf_downloaded, pdf_skipped, len(target_pdf_urls))

    stats = {
        "total_downloaded": total_downloaded,
        "total_skipped": total_skipped,
        "total_failed": total_failed,
        "intervenciones_files": intervenciones_downloaded,
        "pdfs_downloaded": pdf_downloaded,
        "pdfs_skipped": pdf_skipped,
        "legislatures": legs_summary,
    }
    logger.info("Congreso extraction complete: %s", stats)
    return stats
