# ENTSO-E European Day-Ahead Prices and Actual Load

[Published dataset on Hugging Face](https://huggingface.co/datasets/hsilvosa/entsoe-day-ahead)

This directory contains a reproducible pipeline for collecting, normalizing, profiling, and publishing electricity-market data from the ENTSO-E Transparency Platform. The initial release covers day-ahead prices and actual total load for European bidding zones from 1 January 2015 through the latest complete month configured for the snapshot.

The data is observational. It has no target label, predefined classes, or official train, validation, and test split. Each table is published as one `train` split so that downstream users can create task-specific temporal splits without hidden leakage.

## Source and attribution

- Transparency Platform: <https://transparency.entsoe.eu/>
- ENTSO-E transparency overview: <https://www.entsoe.eu/data/transparency-platform/>
- API endpoint: <https://web-api.tp.entsoe.eu/api>
- Publisher: European Network of Transmission System Operators for Electricity (ENTSO-E)

ENTSO-E states that the platform publishes electricity generation, load, transmission, and balancing information under the European transparency framework. Users must review the current Transparency Platform terms before redistributing a release. The Hugging Face card therefore uses `license: other` until the exact applicable terms are mapped to a standard identifier.

## Dataset contents

The release has two configurations:

| Configuration | Rows | Coverage | Compressed Parquet | Unit and description |
|---|---:|---|---:|---|
| `day_ahead_prices` | 5,423,638 | 45 zones in 31 countries | 218.04 MB | Day-ahead market prices by bidding zone and delivery interval, in the source currency/MWh |
| `actual_load` | 7,690,918 | 48 zones in 34 countries | 334.64 MB | Actual total electricity load by bidding zone and interval, in MW |

The complete snapshot contains 13,114,556 rows in 27 Parquet shards and occupies 552.67 MB. Its temporal coverage is 1 January 2015 through 31 July 2026. The source download completed 7,550 concurrent, resumable API tasks in 92 minutes: 6,183 responses contained data, 1,367 reported no matching data, and none failed.

Observed source resolutions are 15, 30, and 60 minutes. Price currencies are EUR, RON, BGN, and PLN. Day-ahead prices range from -500 to 6,101.78 in the corresponding source currency per MWh; negative prices are valid. Actual load ranges from 0 to 94,492 MW and has no negative observations. Detailed counts by zone and country, numeric summaries, schemas, provenance, quality checks, and checksums are available under `artifacts/`.

Every row contains a stable record identifier, UTC timestamp, zone key and name, country code, EIC area code, source resolution, unit, business, contract, auction and classification codes, document and revision identifiers, time-series identifier, and source-file reference. Prices additionally preserve the source currency. The `day_ahead_prices` table keeps daily contracts (`A01`) and excludes explicitly identified intraday contracts (`A07`).

The pipeline does not resample or impute observations. Hourly, half-hourly, and quarter-hourly values retain their original resolution. Negative electricity prices are valid. Negative load values fail the quality checks.

## Credentials

API access requires an ENTSO-E security token. Store it in the `.env` file at the root of this repository:

```dotenv
ENTSOE_API_TOKEN=your-token
```

The root `.env` is ignored by Git. The token is added only to the outgoing query and is excluded from filenames, manifests, provenance, logs, exceptions, Parquet files, and Hugging Face staging.

## Installation

Python 3.11 or newer is recommended.

```bash
cd entsoe-transparency
python -m venv .venv
python -m pip install -e ".[dev]"
```

## Usage

Inspect the planned number of requests without using the token:

```bash
entsoe-pipeline estimate --config configs/default.json
```

Run the six-request sample first:

```bash
entsoe-pipeline run --config configs/sample.json
```

Run the full snapshot:

```bash
entsoe-pipeline run --config configs/default.json
```

Stages can also be executed independently:

```bash
entsoe-pipeline download --config configs/default.json
entsoe-pipeline normalize --config configs/default.json
entsoe-pipeline analyze --config configs/default.json
entsoe-pipeline stage --config configs/default.json
```

The downloader is concurrent and resumable. It uses separate tasks by dataset, bidding zone, and period, validates cached XML before reuse, retries temporary failures with exponential backoff, and writes a progress ETA every 25 completed tasks. Day-ahead prices use monthly requests; load uses annual requests to reduce API calls.

Inspect `hf_staging/` before publication. Uploading is deliberately separate:

```bash
entsoe-pipeline upload --config configs/default.json --repo-id ORGANIZATION/DATASET_NAME
```

## Storage lifecycle

Raw XML, normalized Parquet, virtual environments, and Hugging Face staging directories are excluded by the repository `.gitignore`. After a verified publication, they can be removed locally because the acquisition code, configuration, schemas, profile, provenance, quality report, and checksums remain reproducible.

## Limitations

ENTSO-E data availability and resolution vary by bidding zone and period. Zone definitions change over time, source documents can be revised, and individual intervals can be absent. The configured historical Germany-Austria-Luxembourg area ends on 1 October 2018 and the Germany-Luxembourg area begins on that date. Other market-boundary changes may require future configuration updates.

The latest incomplete calendar month is excluded from the default snapshot. This dataset is intended for research and historical analysis, not operational dispatch, trading, settlement, safety, or real-time grid control.
