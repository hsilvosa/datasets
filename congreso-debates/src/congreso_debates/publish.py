from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from .config import Config

logger = logging.getLogger(__name__)

README_TEMPLATE = """---
license: other
language:
- es
pretty_name: Congreso de los Diputados de España (Debates, Discursos Literales y Votaciones L1-L15)
tags:
- parliament
- politics
- speeches
- speech-transcripts
- voting-records
- stance-detection
- llm-benchmarks
- spain
- nlp-spanish
configs:
- config_name: intervenciones_discursos
  data_files:
  - split: train
    path: data/intervenciones/*.parquet
- config_name: initiatives
  data_files:
  - split: train
    path: data/initiatives/*.parquet
- config_name: deputy_votes
  data_files:
  - split: train
    path: data/deputy_votes/*.parquet
---

# Congreso de los Diputados de España: Debates, Discursos Literales y Votaciones (L1 a L15)

Dataset estructurado y estandarizado con el histórico del Congreso de los Diputados de España, conteniendo transcripciones literales de debates parlamentarios (extraídas de los Diarios de Sesiones oficiales DSCD), 105.000 votos nominales de diputados por escaño y grupo político, y catálogo de iniciativas legislativas de las Legislaturas I a XV.

## Tablas y Estructura del Dataset

1. **`intervenciones_discursos` (`congreso_intervenciones.parquet`)**:
   - **41.125 intervenciones y discursos parlamentarios** con metadatos completos.
   - **35+ Millones de caracteres de discursos literales (`speech_text`)** extraídos directamente de los Diarios de Sesiones oficiales.
   - Campos: `legislature`, `super_tipo_iniciativa`, `tipo_iniciativa`, `objeto_iniciativa`, `num_expediente`, `autor`, `sesion_date`, `organo`, `fase`, `tipo_intervencion`, `orador`, `cargo_orador`, `inicio_intervencion`, `fin_intervencion`, `speech_text`, `speech_char_count`, `enlace_texto_integro`, `enlace_pdf`.

2. **`deputy_votes` (`congreso_deputy_votes_all.parquet` y por legislatura `L1` a `L15`)**:
   - **105.000 votos nominales individuales** cruzados con diputado, grupo parlamentario, escaño y sentido de voto (Sí, No, Abstención, No vota).

3. **`initiatives` (`congreso_initiatives_all.parquet` y por legislatura `L1` a `L15`)**:
   - **300 iniciativas votadas en pleno**, con recuento de votos, texto de expedientes y acuerdos.

## Aplicaciones de Machine Learning & LLMs

- **Modelado de Lenguaje Político y Discurso**: Fine-tuning y benchmarks en español sobre argumentación retórica y oratoria parlamentaria.
- **Detección de Posturas (Stance Detection)**: Predicción del sentido de voto a partir del texto del discurso o de la iniciativa legislativa.
- **Búsqueda Semántica y RAG Jurídico-Político**: Recuperación precisa de intervenciones y debates por diputado, partido o tema.
- **Análisis de Redes y Disciplina de Voto**: Modelado de coaliciones parlamentarias a lo largo de la democracia española.

## Licencia y Procedencia

Datos públicos procedentes del Portal de Datos Abiertos del Congreso de los Diputados y de los Diarios de Sesiones Oficiales (Ley 37/2007 de reutilización de la información del sector público).
"""


def stage(config: Config) -> dict[str, Any]:
    """Prepare staged directory ready for Hugging Face upload."""
    staging_dir = config.staging_dir
    staging_dir.mkdir(parents=True, exist_ok=True)

    data_dir = staging_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    init_dir = data_dir / "initiatives"
    init_dir.mkdir(parents=True, exist_ok=True)
    dep_dir = data_dir / "deputy_votes"
    dep_dir.mkdir(parents=True, exist_ok=True)
    interv_dir = data_dir / "intervenciones"
    interv_dir.mkdir(parents=True, exist_ok=True)

    for f in config.processed_dir.glob("congreso_initiatives_*.parquet"):
        shutil.copy2(f, init_dir / f.name)

    for f in config.processed_dir.glob("congreso_deputy_votes_*.parquet"):
        shutil.copy2(f, dep_dir / f.name)

    for f in config.processed_dir.glob("congreso_intervenciones*.parquet"):
        shutil.copy2(f, interv_dir / f.name)

    art_staging = staging_dir / "artifacts"
    art_staging.mkdir(parents=True, exist_ok=True)
    for f in config.artifacts_dir.glob("*.json"):
        shutil.copy2(f, art_staging / f.name)

    (staging_dir / "README.md").write_text(README_TEMPLATE, encoding="utf-8")

    manifest = {
        "dataset_name": "congreso-debates-es",
        "staged_at": "2026-08-22T13:20:00Z",
        "files_count": len(list(staging_dir.rglob("*.parquet"))),
        "total_size_mb": sum(f.stat().st_size for f in staging_dir.rglob("*.parquet")) / (1024 * 1024),
    }
    (staging_dir / "UPLOAD_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    logger.info("Dataset staged in %s (%d parquet files, %.2f MB)", staging_dir, manifest["files_count"], manifest["total_size_mb"])
    return {"staging_dir": str(staging_dir)}


def publish(config: Config, repo_id: str, token: str | None = None) -> dict[str, Any]:
    """Publish staged dataset to Hugging Face Hub."""
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    logger.info("Uploading folder %s to Hugging Face repo %s...", config.staging_dir, repo_id)
    api.upload_folder(
        folder_path=str(config.staging_dir),
        repo_id=repo_id,
        repo_type="dataset",
    )
    logger.info("Successfully uploaded dataset to https://huggingface.co/datasets/%s", repo_id)
    return {"status": "published", "repo_url": f"https://huggingface.co/datasets/{repo_id}"}
