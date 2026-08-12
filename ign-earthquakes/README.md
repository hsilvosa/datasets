# IGN Spanish Earthquake Catalogue

This dataset is a research-ready snapshot of the official earthquake catalogue maintained by the Spanish Instituto Geografico Nacional (IGN). It contains 207,222 seismic events from 3 March 1373 through 12 August 2026 within the catalogue search area used by IGN for Spain, the Canary Islands, and nearby regions.

Published dataset: [hsilvosa/ign-earthquakes on Hugging Face](https://huggingface.co/datasets/hsilvosa/ign-earthquakes)

The data is observational and has no target label or predefined classes. The complete table is provided as one `train` split because artificial train, validation, and test partitions would imply a prediction task and could introduce temporal leakage. Researchers should create task-specific temporal or geographic splits.

## Source and attribution

- Official catalogue: <https://www.ign.es/web/sis-catalogo-terremotos>
- Citation: Instituto Geografico Nacional (IGN), Catalogo de terremotos
- DOI: <https://doi.org/10.7419/162.03.2022>

The source requires attribution to IGN. The Hugging Face metadata uses `license: other` until the exact current reuse terms are mapped to a standard Hub identifier. Users must review the IGN data policy before redistributing derived releases.

## Dataset contents

The `earthquakes` configuration contains one row per catalogue event and thirteen columns:

| Column | Description |
|---|---|
| `event_id` | IGN event identifier |
| `occurred_at_utc` | Event date and time normalized to UTC |
| `latitude`, `longitude` | Epicentral coordinates in decimal degrees |
| `depth_km` | Hypocentral depth in kilometres |
| `maximum_intensity` | Original maximum-intensity value when available |
| `maximum_intensity_numeric` | Numeric conversion of the macroseismic intensity or range |
| `magnitude` | Preferred magnitude reported by the catalogue |
| `magnitude_type_code` | Source magnitude-type code |
| `location` | IGN textual location description |
| `country_code`, `country_name` | Country derived from the IGN location suffix, when available |
| `source_format` | `csv`, except for one documented `html_fallback` record |

The staged release includes three Zstandard-compressed Parquet shards, the dataset card, and machine-readable `profile.json`, `schema.json`, `quality.json`, `provenance.json`, and `checksums.json` artifacts. Raw CSV and HTML source responses are not published.

## Snapshot summary

- 207,222 rows and no duplicate event identifiers
- Temporal coverage: 1373-03-03 through 2026-08-12
- Magnitude coverage: 200,848 non-null values, ranging from -2.0 to 8.5
- Depth coverage: 207,221 non-null values, ranging from 0 to 663 km
- Maximum intensity: available for 16,208 events in the original field
- All coordinates pass global latitude and longitude range checks
- Country assignment from the IGN location suffix: Spain 127,315; France 13,872; Portugal 7,464; Morocco 5,417; Algeria 3,380; Andorra 116
- 49,658 maritime, regional, or legacy descriptions have no recognized country suffix and remain unassigned

The full exploratory results, null fractions, distinct counts, numeric summaries, common values, schema, and checksums are available under `artifacts/`.

## Extraction notes

The IGN download endpoint cannot export the complete historical catalogue in one request. The pipeline uses resumable time shards and narrows known problematic historical ranges from decades to years, months, or days. The event `es1427aaaaa` is present in the official result table but omitted by the official CSV exporter even for a single-day query. Its values are therefore parsed from the corresponding official HTML result and marked `html_fallback`; all other 207,221 records come from official CSV exports.

The sample configuration requests one day and limits the result to five rows. The default configuration reproduces this full snapshot:

```bash
cd ign-earthquakes
python -m pip install -e .
python -m ign_earthquakes run --config configs/sample.json
python -m ign_earthquakes run --config configs/default.json
python -m unittest discover -s tests -v
```

## Limitations

IGN continuously revises recent seismic solutions, so later snapshots can change event attributes or counts. Historical event dates, coordinates, intensities, and magnitudes reflect the source catalogue and may have greater uncertainty than instrumentally recorded events. Missing values are preserved rather than imputed. Negative earthquake magnitudes are valid and are not treated as errors.

Country is a conservative derived field based on the location suffix published by IGN. It is not a point-in-polygon determination: descriptions without a suffix, including maritime regions, remain unassigned.

This is a research dataset, not an operational alert feed. It must not be used as the sole source for emergency, safety, engineering, or navigation decisions.
