# BOE and BORME Open Data

This repository contains a reproducible, resumable and append-only pipeline for the open data published by the Spanish Agencia Estatal Boletin Oficial del Estado (AEBOE). It collects the complete published history exposed by the AEBOE Open Data API: the daily summaries (sumarios) of the Boletin Oficial del Estado (BOE) and the Boletin Oficial del Registro Mercantil (BORME), the consolidated legislation catalogue with full consolidated texts, and the auxiliary reference tables.

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

The BOE Open Data API exposes the gazette summaries and the consolidated legislation. This dataset reproduces everything the API exposes, including the document URLs, but it does not mirror the body of every historical gazette document. Consolidated norms can be revised by the publisher; the pipeline records each observed version rather than assuming the current text is definitive. Auxiliary and catalogue endpoints can change over time, so later snapshots can add or restate values. This is a research dataset and is not legal advice; the official and authentic texts are the signed PDFs published by the AEBOE.
