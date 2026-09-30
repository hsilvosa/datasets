# BOE and BORME Detailed: Article-Level Consolidated Legislation

This repository derives detailed, article-level tables from the [hsilvosa/boe-borme](https://huggingface.co/datasets/hsilvosa/boe-borme) release. It reads the consolidated legislation XML that the base release already contains and flattens it into blocks, versioned text fragments, ELI identifiers, and a cross-link between published gazette documents and consolidated norms.

## Coverage notice

This is an article-level derivation of consolidated legislation, not a complete documentary archive of the BOE or BORME. It contains only the legislation XML and observed block versions available in the base release. It does not add the full text of every gazette document, BORME announcement, PDF or attachment, and the document-to-legislation links are not full document texts. Its historical and version coverage inherits the limits of the base dataset; it is not a complete reconstruction of every publication or legal text at every historical date. The separate 2023–2025 archival pilot is incomplete and is not included in this published dataset.

Published dataset: [hsilvosa/boe-borme-detailed on Hugging Face](https://huggingface.co/datasets/hsilvosa/boe-borme-detailed)

The data is observational and has no target label or predefined classes. Every configuration is provided as a single `train` split containing the complete table.

## Source and attribution

- Base dataset: <https://huggingface.co/datasets/hsilvosa/boe-borme>
- Original publisher: Agencia Estatal Boletin Oficial del Estado (AEBOE)
- Open data API: <https://www.boe.es/datosabiertos/api/api.php>

Reuse is subject to the AEBOE legal notice and reuse conditions. The dataset card uses `license: other` until the exact terms are mapped to a standard Hub identifier.

## Configurations

| Configuration | Rows | Description |
|---|---:|---|
| `legislacion_bloques` | 573,899 | One row per block (article, chapter, preamble, annex, ...) of the current consolidated text, with block type, title, ordering, version count, validity dates, and text |
| `legislacion_versiones` | 692,360 | One row per block version: the block text as it stood from `fecha_vigencia` until `fecha_hasta`, plus the identifier of the norm that introduced it |
| `legislacion_eli` | 12,401 | One row per consolidated norm with the ELI identifier decomposed into country, type, year, month, day and ordinal, plus rank, department, scope and consolidation status |
| `documento_legislacion` | 12,061 | Cross-link between the original gazette document (BOE-A) and the consolidated norm, with section, department, title and document URLs |

All tables carry `source_sha256`, `retrieved_at_utc` and `run_id` from the base rows they were derived from.

## How the derivation works

- `legislacion_bloques` and `legislacion_versiones` are parsed from each consolidated norm's `<bloque>` and `<version>` elements. A block is the smallest addressable unit of a consolidated text (`precepto`, `preambulo`, `anexo`, ...). Each version records `fecha_publicacion` and `fecha_vigencia`; `fecha_hasta` is the next version's `fecha_vigencia` within the same block, so a version's validity interval is explicit.
- `legislacion_eli` decomposes the `url_eli` field (for example `https://www.boe.es/eli/es/c/1978/12/27/(1)` yields `es`, `c`, `1978`, `12`, `27`, `1`).
- `documento_legislacion` joins the base sumario documents to the consolidated norms by identifier.

The derivation is deterministic and append-only: shards are keyed by the base source checksums, so re-running only adds shards for new or revised base rows and never rewrites existing files.

## Running the pipeline

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# The base release must exist locally (default: ..\boe-borme\data\processed)
.\.venv\Scripts\python.exe -m boe_borme_detailed run --config configs/default.json

# Individual stages
.\.venv\Scripts\python.exe -m boe_borme_detailed derive  --config configs/default.json
.\.venv\Scripts\python.exe -m boe_borme_detailed analyze --config configs/default.json
.\.venv\Scripts\python.exe -m boe_borme_detailed stage   --config configs/default.json
.\.venv\Scripts\python.exe -m boe_borme_detailed status  --config configs/default.json
```

## Use cases

- Point-in-time legal text: reconstruct what an article said on any date using `fecha_vigencia`/`fecha_hasta`.
- Amendment analysis: which norm introduced each version of each block.
- Legal information retrieval and RAG with article-level granularity and stable block identifiers.
- Citation and ELI analytics across time, rank, department and scope.

## Limitations

- The derivation reflects the consolidated text published by the AEBOE. It is not the authentic text; the signed PDFs are.
- 340 consolidated norms could not be linked to a gazette document because they predate the sumario coverage or are outside it; the link table simply omits them.
- Block identifiers are stable within a norm but not globally meaningful across norms.
- This is a research dataset and is not legal advice.
