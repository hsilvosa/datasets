# OpenPLACSP Historical Procurement

## Dataset summary

OpenPLACSP Historical Procurement contains public procurement notices published by contracting authorities hosted on the Spanish Public Sector Procurement Platform. Every published version of a procurement procedure is retained, including deletion markers, rather than reducing each procedure to its latest state.

The snapshot covers updates from 2 January 2012 through 30 December 2024. It excludes minor contracts, linked documents, and notices published only through external aggregation platforms.

| Property | Value |
| --- | --- |
| Publisher | Directorate-General for State Assets, Spanish Ministry of Finance |
| Geographic scope | Spain |
| Source format | ATOM feeds containing CODICE XML |
| Published format | Zstandard-compressed Parquet |
| Configurations | `versions`, `lots`, `cpv_codes`, `awards` |
| Split | One `train` split per configuration |
| Total rows | 17,104,600 |
| Compressed size | 951.20 MB |

## Dataset structure

The four configurations form a relational historical dataset. `version_id` is the primary key of `versions` and the foreign key used by the other configurations.

| Configuration | Rows | Description |
| --- | ---: | --- |
| `versions` | 2,993,582 | One row per published state or deletion marker |
| `lots` | 2,080,084 | Lots attached to each published version |
| `cpv_codes` | 8,944,813 | CPV classifications at procedure or lot level |
| `awards` | 3,086,121 | Procedure results, winning parties, and awarded amounts |

### Versions

| Fields | Description |
| --- | --- |
| `version_id` | Deterministic identifier for the published version |
| `atom_id` | Identifier of the source ATOM entry |
| `updated_at`, `published_at` | Source update and publication timestamps in UTC |
| `title`, `summary`, `entry_url` | Public description and URL of the source entry |
| `is_deleted` | Whether the row is an ATOM deletion marker |
| `folder_id`, `status_code` | Procurement file number and source status |
| `project_name` | Object or title of the procurement project |
| `contract_type_code`, `contract_subtype_code` | Source contract classification codes |
| `estimated_value`, `budget_tax_exclusive`, `budget_total`, `currency` | Published values, budgets, and currency |
| `procedure_code` | Source procurement procedure code |
| `contracting_party_name`, `contracting_party_nif` | Published authority name and Spanish tax identifier |
| `contracting_party_platform_id`, `contracting_party_type_code` | PLACSP authority identifier and source type |
| `buyer_profile_url` | Public buyer-profile URL |
| `source_archive`, `source_member` | Source ZIP archive and ATOM member |

### Lots

| Fields | Description |
| --- | --- |
| `version_id` | Parent version identifier |
| `lot_id` | Lot identifier within the procedure |
| `name` | Lot name or object |
| `budget_tax_exclusive`, `budget_total`, `currency` | Published lot amounts and currency |

### CPV codes

| Fields | Description |
| --- | --- |
| `version_id` | Parent version identifier |
| `lot_id` | Related lot, or null for a procedure-level classification |
| `cpv_code`, `cpv_name` | Common Procurement Vocabulary code and source label |

### Awards

| Fields | Description |
| --- | --- |
| `version_id` | Parent version identifier |
| `result_position`, `winner_position` | Stable positions within the source version |
| `result_code`, `description` | Published result code and description |
| `award_date`, `received_tenders` | Award decision date and number of tenders received |
| `lot_id` | Related lot when the result is lot-specific |
| `winner_name`, `winner_nif` | Published winner name and Spanish tax identifier |
| `award_tax_exclusive`, `currency` | Published award amount excluding taxes and its currency |

## Version semantics

Repeated `atom_id` and `folder_id` values are expected. Each row in `versions` represents a state published at a particular time. A current-state view can be constructed by selecting the greatest non-null `updated_at` for each `atom_id` and retaining deletion markers when the latest row has `is_deleted = true`.

All configurations use a single `train` split. Random row-level splits would place versions of the same procedure in different partitions and create temporal leakage. Downstream prediction tasks should use time-aware splits and keep all versions of a procedure together.

## Processing

ATOM entries and CODICE elements are normalized into four relational tables. Source values are preserved without currency conversion, inflation adjustment, imputation, or inferred classifications. Linked procurement documents are not included.

Stable version identifiers are computed from the source ATOM identifier, update timestamp, and deletion state. Parquet files use explicit schemas, Zstandard compression, and shards of at most 250,000 rows.

## Quality

All 17,104,600 rows passed the required-field checks. The snapshot contains 79,140 deletion markers, no null values in required identifiers or relationship keys, and 70 Parquet shards with verified SHA-256 checksums.

Machine-readable profiles, schemas, quality results, provenance, and checksums are included under `artifacts/`.

## Known limitations

- The snapshot ends on 30 December 2024 and contains no later notices.
- Coverage is not uniform because contracting authorities joined the platform at different times.
- Fields introduced by later CODICE revisions are absent from older records.
- A procedure may appear many times because every published update is retained.
- Monetary values are not converted or adjusted and should not be aggregated across currencies without conversion.
- Published organization names and tax identifiers are source metadata, not independently verified identity data.
- Linked notices and documents may have changed or become unavailable after the snapshot date.

## Source and reuse

The source data was published by the Directorate-General for State Assets through the Spanish Public Sector Procurement Platform and the Spanish Ministry of Finance open-data catalogue. The source describes the records as public information available for reuse. Attribution to the original publisher and the supplied snapshot provenance must be retained in derived releases.

The card uses `license: other` because the source-specific reuse terms have not been mapped to a standard Hugging Face license identifier. The original publisher remains responsible for the source records; this dataset provides a normalized historical representation.
