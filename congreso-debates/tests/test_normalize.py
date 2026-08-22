from pathlib import Path
from congreso_debates.normalize import normalize_voting_file


def test_normalize_voting_file(tmp_path: Path):
    sample = tmp_path / "votacion.json"
    sample.write_text("""{
  "informacion": {
    "sesion": 10,
    "numeroVotacion": 1,
    "fecha": "15/02/2024",
    "titulo": "Proposición de Ley sobre Transparencia",
    "textoExpediente": "Expediente 121/000001",
    "tituloSubGrupo": "Enmienda a la totalidad",
    "textoSubGrupo": "Texto alternativo"
  },
  "totales": {
    "asentimiento": "No",
    "presentes": 350,
    "afavor": 178,
    "enContra": 170,
    "abstenciones": 2,
    "noVotan": 0
  },
  "votaciones": [
    {
      "asiento": "1001",
      "diputado": "García Pérez, Ana",
      "grupo": "GS",
      "voto": "Sí"
    },
    {
      "asiento": "1002",
      "diputado": "López Sanz, Carlos",
      "grupo": "GP",
      "voto": "No"
    }
  ]
}""", encoding="utf-8")

    init_row, dep_rows = normalize_voting_file(sample, legislature=15)
    assert init_row is not None
    assert init_row["legislature"] == 15
    assert init_row["session_number"] == 10
    assert init_row["vote_number"] == 1
    assert init_row["afavor"] == 178
    assert len(dep_rows) == 2
    assert dep_rows[0]["deputy_name"] == "García Pérez, Ana"
    assert dep_rows[0]["vote"] == "Sí"
    assert dep_rows[1]["parliamentary_group"] == "GP"
