from __future__ import annotations

import bz2
import json
from pathlib import Path

import pyarrow.parquet as pq

from bne_linked_data.analyze import analyze
from bne_linked_data.config import Config
from bne_linked_data.normalize import normalize
from bne_linked_data.publish import stage

LINES = """\
<http://datos.bne.es/resource/XX1> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://datos.bne.es/def/C1005> .
<http://datos.bne.es/resource/XX1> <http://www.w3.org/2000/01/rdf-schema#label> "Miguel de Cervantes"@es .
<http://datos.bne.es/resource/XX1> <http://purl.org/dc/terms/created> "1547"^^<http://www.w3.org/2001/XMLSchema#gYear> .
<http://datos.bne.es/resource/XX2> <http://purl.org/dc/terms/creator> <http://datos.bne.es/resource/XX1> .
"""


def _config(tmp_path: Path) -> Config:
    project = tmp_path / "project"
    (project / "configs").mkdir(parents=True)
    (project / "README.md").write_text("# Project documentation\n", encoding="utf-8")
    (project / "DATASET_CARD.md").write_text("# Test dataset card\n", encoding="utf-8")
    payload = {
        "snapshot_date": "2021-01-21",
        "raw_dir": "data/raw",
        "processed_dir": "data/processed",
        "artifacts_dir": "artifacts",
        "staging_dir": "hf_staging",
        "chunk_rows": 2,
        "max_triples_per_collection": None,
        "timeout_seconds": 10,
        "retries": 1,
        "collections": [
            {
                "name": "authorities",
                "url": "https://example.invalid/authorities.nt.bz2",
                "filename": "authorities.nt.bz2",
                "expected_bytes": 0,
            }
        ],
    }
    path = project / "configs" / "test.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    config = Config.load(path)
    config.raw_dir.mkdir(parents=True)
    config.raw_path(config.collections[0]).write_bytes(bz2.compress(LINES.encode("utf-8")))
    return config


def test_normalize_analyze_and_stage(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result = normalize(config)
    assert result["total_triples"] == 4
    assert result["invalid_lines"] == 0
    shards = sorted(config.processed_path(config.collections[0]).glob("*.parquet"))
    assert len(shards) == 2
    table = pq.read_table(shards)
    assert table.num_rows == 4
    assert set(table.column("object_kind").to_pylist()) == {"iri", "literal"}

    profile = analyze(config)
    assert profile["totals"]["rows"] == 4
    assert profile["collections"]["authorities"]["distinct_subjects"] == 2
    quality = json.loads((config.artifacts_dir / "quality.json").read_text(encoding="utf-8"))
    assert quality["passed"] is True

    staged = stage(config)
    assert (staged / "README.md").exists()
    staged_card = (staged / "README.md").read_text(encoding="utf-8")
    assert "# Test dataset card" in staged_card
    assert "# Project documentation" not in staged_card
    assert len(list((staged / "data" / "authorities").glob("*.parquet"))) == 2


def test_normalize_repairs_bne_wrapped_external_iri(tmp_path: Path) -> None:
    config = _config(tmp_path)
    wrapped = """\
<https://datos.bne.es/resource/XX1> <http://www.w3.org/2004/02/skos/core#closeMatch> <http://data.bnf.fr/ark:/12148/cb12456160r
> .
"""
    config.raw_path(config.collections[0]).write_bytes(bz2.compress(wrapped.encode("utf-8")))

    result = normalize(config)

    assert result["total_triples"] == 1
    assert result["invalid_lines"] == 0
    assert result["collections"][0]["repaired_wrapped_iris"] == 1
    table = pq.read_table(sorted(config.processed_path(config.collections[0]).glob("*.parquet")))
    assert table.column("object").to_pylist() == ["http://data.bnf.fr/ark:/12148/cb12456160r"]
    assert table.column("source_line").to_pylist() == [1]
