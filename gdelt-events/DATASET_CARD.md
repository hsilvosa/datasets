# GDELT 1.0 Events: historical snapshot through 2026-08-14

This release is a fixed, analysis-ready snapshot of the complete GDELT 1.0 Event Database. It contains 889,592,605 machine-coded event records extracted by the GDELT Project from worldwide news reporting. The original tab-delimited archives have been normalized to one typed, 59-column schema and stored as Zstandard-compressed Parquet.

Each row describes an action by one actor toward another using the CAMEO taxonomy. Fields cover actor codes, event codes, the four CAMEO quad classes, Goldstein scores, mention and source counts, tone, three sets of geographic attributes, and a source URL when GDELT supplies one.

## Snapshot at a glance

| Item | Value |
| --- | ---: |
| Rows | 889,592,605 |
| Columns | 59 |
| Parquet shards | 929 |
| Compressed Parquet size | 45.22 GB (42.12 GiB) |
| Source archives used | 4,974 |
| Source archive period | 1979 to 2026-08-14 |
| Event date field | 1920-01-01 to 2026-08-14 |
| Invalid action coordinates | 0 |
| Null `global_event_id` values | 0 |

The event date minimum is not a claim that the collection starts in 1920. See the temporal anomaly described under Limitations.

## What is included

- Complete GDELT 1.0 annual archives for 1979–2005.
- Complete monthly archives from January 2006 through March 2013.
- Daily export archives from 2013-04-01 through 2026-08-14.
- One consistent schema for the 57-column historical and 58-column daily layouts.
- A `source_archive` column that traces every row to its GDELT ZIP filename.
- Machine-readable schema, quality, provenance, checksums, and analysis under `artifacts/`.

The reduced 1979–2013 country-level aggregation is deliberately excluded because it overlaps the complete event collection. GKG, Mentions, and GDELT 2.0 are separate GDELT products and are not included.

## Analysis of this snapshot

These figures were computed over every row, not from a sample. The complete results are available in `artifacts/analysis.json`.

### CAMEO quad classes

| Quad class | Meaning | Rows | Share |
| ---: | --- | ---: | ---: |
| 1 | Verbal cooperation | 548,557,724 | 61.66% |
| 2 | Material cooperation | 100,672,989 | 11.32% |
| 3 | Verbal conflict | 113,689,729 | 12.78% |
| 4 | Material conflict | 126,672,161 | 14.24% |

Two source rows contain quad class `0`; consumers should treat this value as unknown.

### Field coverage

| Field | Non-null rows | Coverage |
| --- | ---: | ---: |
| `event_date` | 889,592,605 | 100.00% |
| `action_geo_country_code` | 867,281,220 | 97.49% |
| `action_geo_longitude` | 856,576,142 | 96.29% |
| `action_geo_latitude` | 856,384,267 | 96.27% |
| `actor1_code` | 806,059,856 | 90.61% |
| `source_url` | 676,683,640 | 76.07% |
| `actor2_code` | 653,372,914 | 73.45% |

Missing actor or source fields are expected in GDELT and do not necessarily indicate processing failure.

### Selected temporal counts

| Coded event year | Rows |
| ---: | ---: |
| 1979 | 430,941 |
| 1990 | 1,126,957 |
| 2000 | 4,540,506 |
| 2010 | 22,510,551 |
| 2015 | 66,290,798 |
| 2020 | 44,648,633 |
| 2025 | 40,729,739 |
| 2026 through August 14 | 23,039,749 |

Counts increase sharply over the historical period as the volume and composition of monitored news changes. They must be normalized before making comparisons across time or countries. GDELT publishes normalization files for this purpose.

### Most frequent root event codes

| CAMEO root | Meaning | Rows | Share |
| --- | --- | ---: | ---: |
| `04` | Consult | 222,972,461 | 25.06% |
| `01` | Make public statement | 126,267,030 | 14.19% |
| `05` | Engage in diplomatic cooperation | 71,701,013 | 8.06% |
| `03` | Express intent to cooperate | 64,049,679 | 7.20% |
| `02` | Appeal | 63,567,372 | 7.15% |

Across non-null values, the mean Goldstein score is 0.544, the mean number of mentions is 11.93, and the mean `avg_tone` is 0.119. These means summarize event records and should not be interpreted as population estimates.

## Loading the data

Streaming avoids downloading the full 45.22 GB release:

```python
from datasets import load_dataset

events = load_dataset(
    "hsilvosa/gdelt-events",
    split="train",
    streaming=True,
)

for event in events.take(3):
    print(event["event_date"], event["event_code"], event["action_geo_full_name"])
```

To work with a local copy using PyArrow:

```python
from datetime import date

import pyarrow.dataset as ds

events = ds.dataset("data/events", format="parquet")
scanner = events.scanner(
    columns=["event_date", "event_root_code", "action_geo_country_code"],
    filter=ds.field("event_date") >= date(2025, 1, 1),
)
table = scanner.to_table()
```

Because this is a large dataset, prefer projection and predicate pushdown: request only the columns and date range needed by an analysis.

## Data structure

The Parquet files are stored at `data/events/part-*.parquet`. The 59 fields fall into these groups:

- Event identity and time: `global_event_id`, `event_date`, `month_year`, `year`, `fraction_date`, and `date_added`.
- Actors: two parallel groups of actor name, country, group, ethnicity, religion, and role codes.
- Event classification: `is_root_event`, CAMEO event, base, and root codes, `quad_class`, and `goldstein_scale`.
- Media signals: `num_mentions`, `num_sources`, `num_articles`, `avg_tone`, and `source_url`.
- Geography: actor 1, actor 2, and action location groups with type, name, FIPS country and administrative codes, coordinates, and feature ID.
- Lineage: `source_archive`.

Refer to `artifacts/schema.json` for exact names, Arrow types, order, and nullability. Actor country codes use CAMEO codes; geographic country fields use FIPS codes. They are not interchangeable.

## Source and processing

The source is the [GDELT 1.0 Event Database](https://www.gdeltproject.org/data.html). GDELT uses the CAMEO 1.1b3 event taxonomy; consult the [GDELT Event Codebook](https://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf) and [CAMEO manual](https://data.gdeltproject.org/documentation/CAMEO.Manual.1.1b3.pdf) when interpreting codes.

The preparation pipeline:

1. Resolves a fixed source manifest through 2026-08-14.
2. Verifies archive byte sizes, published MD5 values, ZIP integrity, and CSV presence.
3. Reads CSV members directly from each ZIP without extracting them to disk.
4. Converts both source layouts to typed Arrow fields and adds `source_archive`.
5. Writes approximately one million rows per Zstandard-compressed Parquet shard with statistics and dictionary encoding.
6. Checks schema consistency, identifiers, coordinate ranges, coverage, distributions, and SHA-256 checksums.

The raw ZIP files are not redistributed in this release. Provenance and per-shard SHA-256 values are retained under `artifacts/`.

## Known gaps and source anomalies

- `20221110.export.CSV.zip` and `20230323.export.CSV.zip` appear in GDELT's manifests but were unavailable from the source host when this snapshot was built. The other 4,974 expected archives passed validation.
- GDELT's published MD5 for `20230322.export.CSV.zip` did not match the object currently served. The current object's ETag, ZIP integrity, and locally recorded SHA-256 were used and the override is recorded in `artifacts/source_quality.json`.
- There are 536,074 rows dated from 1920-01-01 through 1920-01-06. Direct inspection of the original GDELT files confirms that these values occur in the source, principally in daily archives dated 2020-01-01 through 2020-01-05. They are preserved without correction. Filter or recode them according to the needs of the analysis.
- `source_url` is structurally absent from the 57-column historical layout and may also be missing in later source records.

## Limitations and responsible use

GDELT records what news systems reported and what an automated pipeline inferred from that reporting. A row is not an independently verified real-world fact. False reports, duplicate coverage, extraction errors, ambiguous actors, and imperfect geocoding can all appear in the data.

Coverage is not uniform across time, geography, language, publisher, or event type. A higher row count can reflect more monitored media, repeated reporting, or a pipeline change rather than more real-world activity. Do not compare raw counts across periods or places without an explicit normalization and sensitivity analysis.

GDELT 1.0 updates daily and includes only selected hand-translated foreign-language material. It does not include the full machine-translated stream available in GDELT 2.0. The dataset also contains location and source information about potentially sensitive events. Avoid using it to infer protected traits, target individuals, or make high-stakes decisions without independent evidence and contextual review.

## License and attribution

GDELT's [Terms of Use](https://www.gdeltproject.org/about.html#termsofuse) allow unlimited academic, commercial, and governmental use and permit redistribution. They require any use or redistribution to cite the GDELT Project and link to its website. The Hugging Face license identifier is therefore `other` rather than an SPDX license.

This repository is an independently prepared snapshot and is not an official GDELT publication. Cite GDELT as the data creator and this repository as the specific processed release used.

Suggested GDELT citation:

```bibtex
@inproceedings{leetaru2013gdelt,
  title = {GDELT: Global Data on Events, Location, and Tone, 1979--2012},
  author = {Leetaru, Kalev and Schrodt, Philip A.},
  booktitle = {ISA Annual Convention},
  year = {2013}
}
```

## Reproducibility artifacts

| File | Purpose |
| --- | --- |
| `artifacts/analysis.json` | Full-snapshot distributions, coverage, and numeric summaries |
| `artifacts/profile.json` | Shape, size, and event-date bounds |
| `artifacts/schema.json` | Arrow schema for all 59 fields |
| `artifacts/quality.json` | Row-level and schema validation results |
| `artifacts/source_quality.json` | Source availability, integrity, and checksum exceptions |
| `artifacts/provenance.json` | Snapshot and configuration lineage |
| `artifacts/checksums.json` | SHA-256 for every Parquet shard |

Statistics and availability statements in this card describe the fixed 2026-08-14 snapshot and should not be assumed to describe later GDELT releases.
