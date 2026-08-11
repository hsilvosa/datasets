# AEMPS CIMA Research Dataset

This repository contains the reproducible pipeline used to build the [AEMPS CIMA dataset on Hugging Face](https://huggingface.co/datasets/HSilvosa/aemps-cima). CIMA is the medicine information system maintained by the Spanish Agency of Medicines and Medical Devices (AEMPS).

The source exposes official information about authorized and non-authorized medicines, commercial presentations, active ingredients, ATC codes, pharmaceutical forms, administration routes, regulatory status, safety-related indicators, segmented summaries of product characteristics and patient leaflets.

The project is intended exclusively for research and data exploration. It is not medical advice and must not be used to make prescribing, dispensing, diagnosis, treatment, regulatory, or safety decisions. Users should consult AEMPS and qualified healthcare professionals for current authoritative information.

## Original source and credit

All source records are provided by **Agencia Española de Medicamentos y Productos Sanitarios (AEMPS)** through CIMA.

- CIMA: <https://cima.aemps.es/cima/publico/home.html>
- REST API documentation, version 1.23: <https://cima.aemps.es/cima/resources/docs/CIMA_REST_API.pdf>
- AEMPS open data statement: <https://sede.aemps.gob.es/datos-abiertos/>

AEMPS describes these data as public and reusable, subject where applicable to source attribution. The generated provenance file records the exact retrieval time and source endpoints. Before public release, the maintainer must review the current AEMPS legal notice and set the precise Hugging Face license metadata if a standard license identifier applies.

## Hugging Face contents

The staging process creates one dataset configuration per relational table. Every configuration uses a single `train` split because CIMA is an entity and document collection, not a predefined supervised-learning benchmark.

The current published snapshot contains 1,171,395 normalized rows across nine configurations and occupies approximately 1.08 GB on the Hub.

| Configuration | Rows | Unit and main content |
|---|---:|---|
| `medications` | 25,447 | One registration with regulatory, prescription, safety, dose and form fields |
| `presentations` | 41,996 | One commercial presentation with national code and status fields |
| `active_ingredients` | 33,126 | One medicine–ingredient relationship |
| `excipients` | 54,228 | One medicine–excipient relationship with amount and unit |
| `atc_codes` | 75,830 | One medicine–ATC relationship |
| `administration_routes` | 26,685 | One medicine–route relationship |
| `documents` | 846,744 | One segmented document section in HTML and plain text |
| `document_links` | 55,434 | One official source-document reference |
| `photos` | 11,905 | One packaging or pharmaceutical-form image reference |

No raw API responses are uploaded. The release also includes machine-readable schema, profile, quality, provenance, and checksum files.

This first release is a complete current-state snapshot at the retrieval date. Historical change events are intentionally excluded: they are not required to represent the current catalogue, and collecting the full event register would substantially delay publication. A future release may expose history as a separate dataset configuration.

## Installation

Python 3.11 or newer is recommended.

```bash
cd aemps-cima
python -m venv .venv
python -m pip install -e ".[dev]"
```

## Usage

Run a small end-to-end sample first:

```bash
cima-pipeline run --config configs/sample.json
```

Run the full snapshot:

```bash
cima-pipeline run --config configs/default.json
```

The `run` command downloads, normalizes, profiles, validates, and stages the release. Individual stages are also available:

```bash
cima-pipeline download --config configs/default.json
cima-pipeline normalize --config configs/default.json
cima-pipeline analyze --config configs/default.json
cima-pipeline stage --config configs/default.json
```

The default configuration excludes the historical change register. Set
`include_change_register` to `true` only when intentionally building a separate historical
release; that endpoint contains more than one million events and is not needed for the
current-state snapshot.

Inspect `hf_staging/` before publishing. Uploading is deliberately separate and explicit:

```bash
cima-pipeline upload --config configs/default.json --repo-id ORGANIZATION/DATASET_NAME
```

Set `HF_TOKEN` in the environment or authenticate with the Hugging Face CLI. The upload command never includes `data/raw`.

The repository intentionally contains no dataset payload. Generated raw responses, Parquet files, and the Hugging Face staging directory are excluded by `.gitignore`. The small JSON files under `artifacts/` preserve the published release profile, schema, provenance, quality results, and checksums for inspection without downloading the dataset.

## Storage lifecycle

After a release is verified on Hugging Face, delete `data/raw`, `data/processed`, and `hf_staging` locally. They are reproducible and ignored by Git. Keep the code, configuration, schemas, tests, and lightweight `artifacts` metadata in the repository.

## Splits, classes, and limitations

There is no target label and therefore no class count. Fields such as ATC group, regulatory state, prescription status, and pharmaceutical form are categorical attributes, not benchmark classes. All configurations contain a 100% `train` split. Researchers creating prediction tasks should define their own patient-safe, leakage-aware, and preferably temporal evaluation design.

CIMA changes over time. A snapshot can become outdated, records may be corrected retrospectively, text availability varies by medicine, and relationships reflect the source representation at retrieval time. Dates returned by the API require careful timezone interpretation. The pipeline preserves source values and records its normalization decisions.
