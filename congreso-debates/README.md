---
license: cc-by-4.0
language:
- es
pretty_name: "Spanish Congress of Deputies: Parliamentary Debates, Verbatim Speeches and Voting Records (L1-L15)"
task_categories:
- text-generation
- text-classification
- feature-extraction
- tabular-classification
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
- rag
size_categories:
- 10K<n<100K
configs:
- config_name: intervenciones_discursos
  data_files:
  - split: train
    path: data/intervenciones/*.parquet
- config_name: deputy_votes
  data_files:
  - split: train
    path: data/deputy_votes/*.parquet
- config_name: initiatives
  data_files:
  - split: train
    path: data/initiatives/*.parquet
---

# Spanish Congress of Deputies: Debates, Verbatim Speeches, and Voting Records (L1 to L15)

High-fidelity dataset containing the parliamentary archive of the Spanish Congress of Deputies (Congreso de los Diputados de España) from the Constituent Legislature / L1 (1979) to the present day (L15).

It includes **41,125 parliamentary interventions** with over **188.6 million characters of verbatim speech text** extracted across all 1,028 official Daily of Sessions (Diario de Sesiones) PDFs, alongside **105,000 nominal deputy voting records** crossed with seat assignments and parliamentary groups.

---

## Dataset Summary

| Configuration | Rows | Historical Range | Key Metrics | Parquet Size |
| :--- | :--- | :--- | :--- | :--- |
| **`intervenciones_discursos`** | **41,125 speeches** | L1 to L15 (1979–2026) | **188,679,518 characters** of verbatim spoken text (`speech_text`), 1,191 unique speakers | **7.63 MB** |
| **`deputy_votes`** | **105,000 votes** | L1 to L15 (15 Legislatures) | Individual voting records (Yes, No, Abstain, Did not vote) by deputy, seat, and group | **23.8 KB (all) / 15 subsets** |
| **`initiatives`** | **300 initiatives** | L1 to L15 | Legislative dossiers, official titles, and plenary vote counts | **7.8 KB (all) / 15 subsets** |

---

## Data Structure and Schema

### 1. `intervenciones_discursos` (`congreso_intervenciones.parquet`)
Contains parliamentary interventions with inlined verbatim spoken transcripts:

```json
{
  "legislature": "Leg.15",
  "sesion_date": "29/02/2024",
  "organo": "Pleno",
  "super_tipo_iniciativa": "Tratados y convenios internacionales",
  "tipo_iniciativa": "Convenio internacional",
  "objeto_iniciativa": "Denuncia del Tratado de la Carta de la Energía, hecho en Lisboa el 17 de diciembre de 1994.",
  "num_expediente": "110/000001",
  "autor": "Gobierno",
  "fase": "Debate de totalidad",
  "tipo_intervencion": "Intervención",
  "orador": "Requena Ruiz, Juan Diego",
  "cargo_orador": "Diputado",
  "inicio_intervencion": "10:15:00",
  "fin_intervencion": "10:27:00",
  "speech_text": "DEBATES DE TOTALIDAD DE CONVENIOS INTERNACIONALES...\nLa señora PRESIDENTA: Pasamos al siguiente punto del orden del día...",
  "speech_char_count": 4820,
  "enlace_texto_integro": "https://www.congreso.es/...",
  "enlace_pdf": "https://www.congreso.es/public_oficiales/L15/CONG/DS/PL/DSCD-15-PL-25.PDF#page=12"
}
```

### 2. `deputy_votes` (`congreso_deputy_votes_all.parquet`)
Individual voting records cast in plenary sessions:

```json
{
  "legislature": 15,
  "session_number": 193,
  "vote_number": 2,
  "date": "23/07/2026",
  "title": "Proposición de Ley relativa a la reforma del régimen fiscal...",
  "deputy_name": "Sánchez Pérez-Castejón, Pedro",
  "parliamentary_group": "GS",
  "seat": "1101",
  "vote": "Sí"
}
```

### 3. `initiatives` (`congreso_initiatives_all.parquet`)
Metadata and plenary voting results for legislative initiatives:

```json
{
  "legislature": 15,
  "session_number": 193,
  "vote_number": 2,
  "date": "23/07/2026",
  "title": "Proposición de Ley relativa a la reforma del régimen fiscal...",
  "expediente": "122/000045",
  "subgroup_title": "",
  "subgroup_text": "",
  "asentimiento": "No",
  "presentes": 350,
  "afavor": 178,
  "en_contra": 170,
  "abstenciones": 2,
  "no_votan": 0
}
```

---

## Usage

### With Python (`pandas` / `polars` / `pyarrow`):

```python
import pandas as pd

# Load verbatim speeches and debates
df_speeches = pd.read_parquet("data/intervenciones/congreso_intervenciones.parquet")

# Filter plenary debates
plenary_debates = df_speeches[df_speeches["organo"] == "Pleno"]
print(f"Total plenary debates: {len(plenary_debates)}")

# Load nominal voting records
df_votes = pd.read_parquet("data/deputy_votes/congreso_deputy_votes_all.parquet")

# Calculate voting distribution across parliamentary groups
voting_dist = df_votes.groupby(["parliamentary_group", "vote"]).size().unstack(fill_value=0)
print(voting_dist)
```

### With Hugging Face `datasets`:

```python
from datasets import load_dataset

# Load verbatim speeches
dataset_speeches = load_dataset("hsilvosa/congreso-debates", "intervenciones_discursos", split="train")

# Load voting records
dataset_votes = load_dataset("hsilvosa/congreso-debates", "deputy_votes", split="train")
```

---

## Machine Learning and NLP Use Cases

- **Spanish LLM Fine-Tuning and Evaluation**: Training and evaluating language models on formal rhetoric, parliamentary debate, and legal reasoning in Spanish.
- **Stance Detection**: Predicting plenary voting behavior (`Yes` / `No` / `Abstain`) directly from speech transcripts and debate text.
- **Legal and Political RAG Systems**: Semantic search over historical interventions with exact page citations to official proceedings.
- **Quantitative Political Science**: Quantifying party cohesion, voting discipline, and ideological polarization over 45 years of democratic parliament.

---

## Data Collection and Cleaning Methodology

1. **Ingestion**: Automated query of the official Open Data API from the Congress of Deputies.
2. **Document Retrieval**: Download of 1,028 official Daily of Sessions (Diario de Sesiones) PDFs.
3. **Multi-process Extraction**:
   - Extraction of target speech pages using multi-process parallelization across CPU cores.
   - Text normalization with regular expressions removing official document headers, running banners, and pagination stamps.
   - Serialization to typed Apache Parquet with Zstandard compression.

---

## Provenance and License

- **Source**: [Congreso de los Diputados Open Data Portal](https://www.congreso.es/datos-abiertos) and Official Diarios de Sesiones (Cortes Generales).
- **License**: Public sector information re-use (Spanish Law 37/2007, EU Directive 2019/1024). Distributed under **Creative Commons Attribution 4.0 International (CC-BY 4.0)**.
