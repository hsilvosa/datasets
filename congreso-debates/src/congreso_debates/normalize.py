from __future__ import annotations

import io
import json
import logging
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pypdf

from .config import Config

logger = logging.getLogger(__name__)

INITIATIVES_SCHEMA = pa.schema([
    ("legislature", pa.int16()),
    ("session_number", pa.int32()),
    ("vote_number", pa.int32()),
    ("date", pa.string()),
    ("title", pa.string()),
    ("expediente", pa.string()),
    ("subgroup_title", pa.string()),
    ("subgroup_text", pa.string()),
    ("asentimiento", pa.string()),
    ("presentes", pa.int32()),
    ("afavor", pa.int32()),
    ("en_contra", pa.int32()),
    ("abstenciones", pa.int32()),
    ("no_votan", pa.int32()),
])

DEPUTY_VOTES_SCHEMA = pa.schema([
    ("legislature", pa.int16()),
    ("session_number", pa.int32()),
    ("vote_number", pa.int32()),
    ("date", pa.string()),
    ("title", pa.string()),
    ("deputy_name", pa.string()),
    ("parliamentary_group", pa.string()),
    ("seat", pa.string()),
    ("vote", pa.string()),
])

INTERVENCIONES_SCHEMA = pa.schema([
    ("legislature", pa.string()),
    ("super_tipo_iniciativa", pa.string()),
    ("tipo_iniciativa", pa.string()),
    ("objeto_iniciativa", pa.string()),
    ("num_expediente", pa.string()),
    ("autor", pa.string()),
    ("sesion_date", pa.string()),
    ("organo", pa.string()),
    ("fase", pa.string()),
    ("tipo_intervencion", pa.string()),
    ("orador", pa.string()),
    ("cargo_orador", pa.string()),
    ("inicio_intervencion", pa.string()),
    ("fin_intervencion", pa.string()),
    ("speech_text", pa.string()),  # Inlined verbatim spoken text from Diario de Sesiones
    ("speech_char_count", pa.int32()),
    ("enlace_texto_integro", pa.string()),
    ("enlace_pdf", pa.string()),
])


def normalize_voting_file(file_path: Path, legislature: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Error reading %s: %s", file_path.name, exc)
        return None, []

    info = data.get("informacion") or {}
    totales = data.get("totales") or {}
    deputies = data.get("votaciones") or []

    session_num = int(info.get("sesion") or 0)
    vote_num = int(info.get("numeroVotacion") or 0)
    v_date = str(info.get("fecha") or "")
    title = str(info.get("titulo") or "")
    expediente = str(info.get("textoExpediente") or "")
    sub_title = str(info.get("tituloSubGrupo") or "")
    sub_text = str(info.get("textoSubGrupo") or "")

    initiative_row = {
        "legislature": legislature,
        "session_number": session_num,
        "vote_number": vote_num,
        "date": v_date,
        "title": title,
        "expediente": expediente,
        "subgroup_title": sub_title,
        "subgroup_text": sub_text,
        "asentimiento": str(totales.get("asentimiento") or "No"),
        "presentes": int(totales.get("presentes") or 0),
        "afavor": int(totales.get("afavor") or 0),
        "en_contra": int(totales.get("enContra") or 0),
        "abstenciones": int(totales.get("abstenciones") or 0),
        "no_votan": int(totales.get("noVotan") or 0),
    }

    deputy_rows = []
    for dep in deputies:
        deputy_rows.append({
            "legislature": legislature,
            "session_number": session_num,
            "vote_number": vote_num,
            "date": v_date,
            "title": title,
            "deputy_name": str(dep.get("diputado") or "").strip(),
            "parliamentary_group": str(dep.get("grupo") or "").strip(),
            "seat": str(dep.get("asiento") or "").strip(),
            "vote": str(dep.get("voto") or "").strip(),
        })

    return initiative_row, deputy_rows


def extract_specific_pdf_pages(args: tuple[str, list[int]]) -> list[tuple[str, int, str]]:
    """Extract and clean only the requested pages from a PDF. Top-level for multiprocessing."""
    pdf_path_str, pages = args
    pdf_path = Path(pdf_path_str)
    pdf_name = pdf_path.name
    results = []
    try:
        reader = pypdf.PdfReader(pdf_path_str)
        total_p = len(reader.pages)
        for p_num in pages:
            if 1 <= p_num <= total_p:
                raw = reader.pages[p_num - 1].extract_text() or ""
                cleaned = re.sub(r"DIARIO DE SESIONES DEL CONGRESO DE LOS DIPUTADOS[^\n]*\n", "", raw)
                cleaned = re.sub(r"PLENO Y DIPUTACI[^\n]*\n", "", cleaned)
                cleaned = re.sub(r"N[úu]m\.\s*\d+\s+[^\n]*P[áa]g\.\s*\d+", "", cleaned)
                results.append((pdf_name, p_num, cleaned.strip()))
    except Exception:
        pass
    return results


def normalize(config: Config) -> dict[str, Any]:
    """Normalize raw JSON voting, interventions, and inlined verbatim speech texts to Parquet."""
    config.processed_dir.mkdir(parents=True, exist_ok=True)

    all_initiatives: list[dict[str, Any]] = []
    all_deputy_votes: list[dict[str, Any]] = []

    # 1. Normalize voting records
    for leg_dir in sorted(config.raw_dir.glob("L*")):
        m = re.search(r"L(\d+)", leg_dir.name)
        if not m:
            continue
        leg = int(m.group(1))
        json_files = sorted(leg_dir.glob("*.json"))

        leg_initiatives = []
        leg_deputy_votes = []

        for jf in json_files:
            init_row, dep_rows = normalize_voting_file(jf, leg)
            if init_row:
                leg_initiatives.append(init_row)
                all_initiatives.append(init_row)
            leg_deputy_votes.extend(dep_rows)
            all_deputy_votes.extend(dep_rows)

        if leg_initiatives:
            out_init = config.processed_dir / f"congreso_initiatives_L{leg}.parquet"
            pq.write_table(pa.Table.from_pylist(leg_initiatives, schema=INITIATIVES_SCHEMA), out_init, compression="zstd")

        if leg_deputy_votes:
            out_dep = config.processed_dir / f"congreso_deputy_votes_L{leg}.parquet"
            pq.write_table(pa.Table.from_pylist(leg_deputy_votes, schema=DEPUTY_VOTES_SCHEMA), out_dep, compression="zstd")

    if all_initiatives:
        out_init_all = config.processed_dir / "congreso_initiatives_all.parquet"
        pq.write_table(pa.Table.from_pylist(all_initiatives, schema=INITIATIVES_SCHEMA), out_init_all, compression="zstd")

    if all_deputy_votes:
        out_dep_all = config.processed_dir / "congreso_deputy_votes_all.parquet"
        pq.write_table(pa.Table.from_pylist(all_deputy_votes, schema=DEPUTY_VOTES_SCHEMA), out_dep_all, compression="zstd")

    # 2. Read primary interventions catalog and collect required PDF pages
    intervenciones_rows: list[dict[str, Any]] = []
    intervenciones_raw_dir = config.raw_dir / "intervenciones"
    pdf_raw_dir = config.raw_dir / "diarios_pdf"

    target_catalog = intervenciones_raw_dir / "IntervencionesIniciativa__20260822050053.json"
    if not target_catalog.exists():
        catalogs = list(intervenciones_raw_dir.glob("*.json"))
        target_catalog = catalogs[0] if catalogs else None

    items = []
    needed_pdf_pages: dict[str, set[int]] = {}

    if target_catalog and target_catalog.exists():
        try:
            items = json.loads(target_catalog.read_text(encoding="utf-8"))
            if isinstance(items, list):
                for item in items:
                    pdf_url = str(item.get("ENLACEPDF") or "")
                    if pdf_url and ".PDF" in pdf_url.upper():
                        pdf_name = Path(pdf_url.split("#")[0]).name
                        page_match = re.search(r"page=(\d+)", pdf_url)
                        page_num = int(page_match.group(1)) if page_match else 1
                        needed_pdf_pages.setdefault(pdf_name, set()).add(page_num)
        except Exception as exc:
            logger.warning("Error reading target catalog %s: %s", target_catalog.name, exc)

    # 3. Multi-process page extraction across all CPU cores
    pdf_page_texts: dict[tuple[str, int], str] = {}
    if pdf_raw_dir.exists() and needed_pdf_pages:
        tasks = []
        for pdf_name, p_set in needed_pdf_pages.items():
            pf = pdf_raw_dir / pdf_name
            if pf.exists():
                tasks.append((str(pf), sorted(list(p_set))))

        logger.info("Extracting %d unique speech start pages across %d downloaded Diario de Sesiones PDFs on all CPU cores...", sum(len(s) for _, s in tasks), len(tasks))
        try:
            with ProcessPoolExecutor() as pool:
                for batch_res in pool.map(extract_specific_pdf_pages, tasks, chunksize=16):
                    for pdf_name, p_num, text in batch_res:
                        pdf_page_texts[(pdf_name, p_num)] = text
        except Exception as exc:
            logger.warning("Multiprocessing fallback to sequential: %s", exc)
            for t in tasks:
                for pdf_name, p_num, text in extract_specific_pdf_pages(t):
                    pdf_page_texts[(pdf_name, p_num)] = text

        logger.info("Indexed %d speech pages into memory successfully", len(pdf_page_texts))

    # 4. Map inlined speech texts to all interventions
    for item in items:
        pdf_url = str(item.get("ENLACEPDF") or "")
        speech_text = ""

        if pdf_url and ".PDF" in pdf_url.upper():
            pdf_name = Path(pdf_url.split("#")[0]).name
            page_match = re.search(r"page=(\d+)", pdf_url)
            page_num = int(page_match.group(1)) if page_match else 1
            speech_text = pdf_page_texts.get((pdf_name, page_num), "")

        intervenciones_rows.append({
            "legislature": str(item.get("LEGISLATURA") or ""),
            "super_tipo_iniciativa": str(item.get("SUPERTIPOINICIATIVA") or ""),
            "tipo_iniciativa": str(item.get("TIPOINICIATIVA") or ""),
            "objeto_iniciativa": str(item.get("OBJETOINICIATIVA") or ""),
            "num_expediente": str(item.get("NUMEXPEDIENTE") or ""),
            "autor": str(item.get("AUTOR") or ""),
            "sesion_date": str(item.get("SESION") or ""),
            "organo": str(item.get("ORGANO") or ""),
            "fase": str(item.get("FASE") or ""),
            "tipo_intervencion": str(item.get("TIPOINTERVENCION") or ""),
            "orador": str(item.get("ORADOR") or ""),
            "cargo_orador": str(item.get("CARGOORADOR") or ""),
            "inicio_intervencion": str(item.get("INICIOINTERVENCION") or ""),
            "fin_intervencion": str(item.get("FININTERVENCION") or ""),
            "speech_text": speech_text,
            "speech_char_count": len(speech_text),
            "enlace_texto_integro": str(item.get("ENLACETEXTOINTEGRO") or ""),
            "enlace_pdf": pdf_url,
        })

    if intervenciones_rows:
        out_interv = config.processed_dir / "congreso_intervenciones.parquet"
        pq.write_table(pa.Table.from_pylist(intervenciones_rows, schema=INTERVENCIONES_SCHEMA), out_interv, compression="zstd")
        speeches_with_text = sum(1 for r in intervenciones_rows if r["speech_char_count"] > 0)
        logger.info("Wrote %d speeches to %s (%d with inlined verbatim speech text)", len(intervenciones_rows), out_interv.name, speeches_with_text)

    return {
        "total_initiatives": len(all_initiatives),
        "total_deputy_votes": len(all_deputy_votes),
        "total_intervenciones": len(intervenciones_rows),
    }
