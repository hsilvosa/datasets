# OpenPLACSP historical procurement

This directory contains a reproducible pipeline for the open procurement notices published by the Spanish Public Sector Procurement Platform. It retains every published update instead of reducing each procurement file to its latest state.

The primary source is the [Ministry of Finance open-data catalogue](https://www.hacienda.gob.es/es-ES/GobiernoAbierto/Datos%20Abiertos/Paginas/licitaciones_plataforma_contratacion.aspx). The main collection covers notices published by contracting authorities hosted on the platform from 1 January 2012 onward. Closed years are distributed as annual ZIP archives; the current year is distributed in monthly ZIP archives and updated daily.

No API key or account is required.

## Scope

The first release covers procurement notices from contracting authorities hosted on PLACSP, excluding minor contracts. The source records a new ATOM entry whenever a notice changes, so repeated procurement identifiers are expected and meaningful.

The normalized release contains:

- `versions`: one row per published version or deletion marker;
- `lots`: lots attached to each version;
- `cpv_codes`: CPV classifications at procurement or lot level;
- `awards`: procedure results and winning parties.

The verified 2012–2024 snapshot contains 17,104,600 rows across the four tables and occupies 951.20 MB in Zstandard-compressed Parquet:

- 2,993,582 published versions, including 79,140 deletion markers;
- 2,080,084 lots;
- 8,944,813 CPV relationships;
- 3,086,121 award and result rows.

The observed update interval runs from 2 January 2012 through 30 December 2024. All required identifiers and relationship keys passed the generated quality checks.

Linked tender documents are not downloaded. The release contains public procurement metadata and business identifiers published by the source. Users must not interpret publication as an endorsement or as a current statement when a newer version exists.

## Reuse conditions

The source describes the information as public and available for reuse. Before publication, the maintainer must review the current Ministry and PLACSP legal notices and record the precise applicable terms. The generated dataset card therefore uses `license: other` until that review is complete.

## Usage

```powershell
cd openplacsp
python -m pip install -e .
openplacsp-pipeline estimate --config configs/default.json
openplacsp-pipeline download --config configs/default.json
openplacsp-pipeline normalize --config configs/default.json
openplacsp-pipeline analyze --config configs/default.json
openplacsp-pipeline stage --config configs/default.json
```

Downloads are resumable and cached. Normalization reads the archived ATOM files directly from ZIP without extracting them. Parquet output is sharded and compressed with Zstandard. The pipeline preserves source ZIP archives locally but excludes them from the staged Hugging Face release.

The verified default snapshot covers 2012 through 2024. At retrieval time, the source firewall returned a short `Request Rejected` HTML page for the advertised 2025 annual and monthly ZIP URLs, although the current ATOM feed remained available. `configs/latest.json` retains the complete 2012 through August 2026 plan so the recent packages can be resumed when the publisher restores automated access or after the official ZIP files are placed in the raw directory manually.

To upload an inspected staging directory, authenticate with the current `hf` CLI and run:

```powershell
openplacsp-pipeline upload --config configs/default.json --repo-id ORGANIZATION/DATASET_NAME
```

All configurations use a single `train` split. Artificial random splits would mix different versions of the same procurement procedure and introduce temporal leakage.
