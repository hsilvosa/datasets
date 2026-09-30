from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from boe_borme_detailed.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_path(name: str) -> Path:
    return FIXTURES / name


def load_text(name: str) -> str:
    return fixture_path(name).read_text(encoding="utf-8")


@pytest.fixture
def make_config(tmp_path):
    def factory(**overrides) -> Config:
        base = {
            "base_processed_dir": tmp_path / "base",
            "processed_dir": tmp_path / "processed",
            "artifacts_dir": tmp_path / "artifacts",
            "state_dir": tmp_path / "state",
            "staging_dir": tmp_path / "staging",
        }
        base.update(overrides)
        config = Config(**base)
        config.validate()
        return config

    return factory


def write_base_tables(
    config,
    *,
    texts=(("BOE-A-2000-1", "complex_texto.xml", "sha-text-1"),),
    legislacion=(("BOE-A-2000-1", "sha-leg-1", "https://www.boe.es/eli/es/l/2000/01/01/1"),),
    sumario=(("BOE-A-2000-1", "sha-suma-1"),),
) -> None:
    retrieved = datetime(2024, 1, 1, tzinfo=UTC)

    texto_rows = [
        {
            "id_norma": norm,
            "texto_xml": load_text(fixture),
            "source_sha256": sha,
            "retrieved_at_utc": retrieved,
            "run_id": "run-test",
        }
        for norm, fixture, sha in texts
    ]
    _write(config.base_processed_dir / "boe_legislacion_texto", texto_rows)

    legislacion_rows = [
        {
            "identificador": norm,
            "titulo": f"Norm {norm}",
            "url_eli": eli,
            "url_html_consolidada": f"https://www.boe.es/buscar/act.php?id={norm}",
            "rango_codigo": "1370",
            "rango_texto": "Ley",
            "departamento_codigo": "5140",
            "departamento_texto": "Ministerio de Hacienda",
            "ambito_codigo": "1",
            "ambito_texto": "Estatal",
            "estado_consolidacion_codigo": "3",
            "estado_consolidacion_texto": "Finalizado",
            "vigencia_agotada": "N",
            "fecha_publicacion": date(2000, 1, 1),
            "fecha_disposicion": date(1999, 12, 30),
            "fecha_vigencia": date(2000, 1, 2),
            "source_sha256": sha,
            "retrieved_at_utc": retrieved,
            "run_id": "run-test",
        }
        for norm, sha, eli in legislacion
    ]
    _write(config.base_processed_dir / "boe_legislacion", legislacion_rows)

    sumario_rows = [
        {
            "document_id": doc,
            "publication": "BOE",
            "publication_date": date(2000, 1, 1),
            "issue_id": "BOE-S-2000-1",
            "issue_numero": "1",
            "seccion_codigo": "1",
            "seccion_nombre": "I. Disposiciones generales",
            "departamento_codigo": "5140",
            "departamento_nombre": "MINISTERIO DE HACIENDA",
            "epigrafe_nombre": "Leyes",
            "titulo": f"Document {doc}",
            "url_html": f"https://www.boe.es/diario_boe/txt.php?id={doc}",
            "url_xml": f"https://www.boe.es/diario_boe/xml.php?id={doc}",
            "url_pdf": f"https://www.boe.es/boe/dias/2000/01/01/pdfs/{doc}.pdf",
            "source_sha256": sha,
            "retrieved_at_utc": retrieved,
            "run_id": "run-test",
        }
        for doc, sha in sumario
    ]
    _write(config.base_processed_dir / "boe_sumario", sumario_rows)


def _write(directory: Path, rows: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, directory / "part-base.parquet", compression="zstd")


def dump_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
