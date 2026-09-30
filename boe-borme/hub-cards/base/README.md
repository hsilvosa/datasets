---
license: other
language:
- es
pretty_name: "BOE and BORME Open Data (Spanish Official Gazette and Commercial Registry)"
tags:
- boe
- borme
- legislation
- legal
- public-data
- spain
- spanish
configs:
- config_name: boe_sumario
  data_files:
  - split: train
    path: data/boe_sumario/*.parquet
- config_name: borme_sumario
  data_files:
  - split: train
    path: data/borme_sumario/*.parquet
- config_name: boe_legislacion
  data_files:
  - split: train
    path: data/boe_legislacion/*.parquet
- config_name: boe_legislacion_materias
  data_files:
  - split: train
    path: data/boe_legislacion_materias/*.parquet
- config_name: boe_legislacion_referencias
  data_files:
  - split: train
    path: data/boe_legislacion_referencias/*.parquet
- config_name: boe_legislacion_texto
  data_files:
  - split: train
    path: data/boe_legislacion_texto/*.parquet
- config_name: boe_aux
  data_files:
  - split: train
    path: data/boe_aux/*.parquet
---

# BOE and BORME Open Data

This dataset contains BOE and BORME daily summaries (sumarios), a consolidated legislation catalogue with consolidated texts, and auxiliary reference tables, collected through the Spanish Agencia Estatal Boletin Oficial del Estado (AEBOE) Open Data API. The pipeline is reproducible, resumable and append-only.

## Coverage notice

This is not a complete documentary archive of the BOE or BORME. Gazette sumario rows contain index metadata and document URLs, not the full body of every gazette document or commercial registry announcement. Full-text content is provided for consolidated legislation in `boe_legislacion_texto`; this does not cover all published gazette documents. Historical coverage is limited to the sources and dates acquired for this release, not every year or every AEBOE collection. The separate 2023–2025 archival pilot is incomplete and is not included in this published dataset.


The data is observational and legal in nature and has no target label or predefined classes. Every configuration is provided as a single `train` split containing the complete table. Artificial train, validation and test partitions would imply a prediction task that the source does not define.

## Source and attribution

- Open data API: <https://www.boe.es/datosabiertos/api/api.php>
- BOE sumarios: available from September 1960
- BORME sumarios: available from January 2009
- Publisher: Agencia Estatal Boletin Oficial del Estado (AEBOE)

Reuse is subject to the AEBOE legal notice and reuse conditions (<https://www.boe.es/informacion/aviso_legal/index.php#reutilizacion>). Until the exact terms are mapped to a standard Hub identifier the dataset card uses `license: other`. Review the source terms before redistributing derived releases.

## Configurations

| Configuration | Rows per document | Description |
|---|---|---|
| `boe_sumario` | one per published BOE document | Daily gazette index: section, department, epigraph, title, control code and document URLs |
| `borme_sumario` | one per published BORME entry | Commercial registry announcements: section, subsection, title, company and document URLs |
| `boe_legislacion` | one per consolidated norm version | Norm metadata, scope, department, rank, dates, ELI and consolidation status |
| `boe_legislacion_materias` | one per norm-subject pair | Subject classifications attached to a consolidated norm |
| `boe_legislacion_referencias` | one per relation | Previous and subsequent relations between norms |
| `boe_legislacion_texto` | one per norm version | Full consolidated XML text and a plain-text rendering with block and character counts |
| `boe_aux` | one per code | Auxiliary reference tables (materias, ambitos, estados, departamentos, rangos, relaciones) |

Every table carries `source_sha256`, `retrieved_at_utc` and `run_id`. Revised norms and corrected gazette editions are stored as additional rows rather than overwriting earlier ones; consumers should deduplicate by primary key taking the newest `retrieved_at_utc` when they need the latest state, and keep all versions when they need history.

## Running the pipeline

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# Full historical backfill (all configurations, from the earliest editions to today)
.\.venv\Scripts\python.exe -m boe_borme run --config configs/default.json

# Individual stages
.\.venv\Scripts\python.exe -m boe_borme download  --config configs/default.json
.\.venv\Scripts\python.exe -m boe_borme normalize --config configs/default.json
.\.venv\Scripts\python.exe -m boe_borme analyze   --config configs/default.json
.\.venv\Scripts\python.exe -m boe_borme stage     --config configs/default.json
.\.venv\Scripts\python.exe -m boe_borme status    --config configs/default.json
```

Acquisition uses `max_workers` concurrent requests with a shared minimum interval (`request_delay_seconds`) and exponential backoff. The default configuration uses four workers with a 0.3 second spacing.

### Resumability

Every unit is written atomically and completion is derived from the files on disk. If a run is interrupted, running the same command again continues with the units that are still missing; completed units are not re-downloaded. `status` reports coverage.

### Append-only updates

Re-running the pipeline after it has finished only fetches new and changed units and appends new Parquet shard files. Existing shard files are never rewritten. Corrected editions and revised norms are retained as additional versions, so previously published data is never affected.

### Completeness gate

`analyze` writes `artifacts/quality.json`. `stage` refuses to build a release unless the quality status is `pass`, which requires every planned gazette day, norm, text and auxiliary table to be either retrieved or explicitly recorded as unavailable. A partial dataset is never staged as complete.

## Outputs

The staged release contains Zstandard-compressed Parquet shards under `data/<configuration>/`, the dataset card, and machine-readable `profile.json`, `schema.json`, `quality.json`, `provenance.json` and `checksums.json` artifacts. Raw API responses, acquisition state and credentials are never published.

## Limitations

This release collects gazette summaries, consolidated legislation and auxiliary tables from selected AEBOE Open Data API endpoints. It does not mirror every API resource, the body of every historical gazette document, all PDFs or all attachments. Consolidated norms can be revised by the publisher; observed snapshots do not establish a complete history of every change. Auxiliary and catalogue endpoints can change over time, so later snapshots can add or restate values. This is a research dataset and is not legal advice; the official and authentic texts are the signed PDFs published by the AEBOE.
