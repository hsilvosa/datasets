# Safecast Historical Radiation Measurements

## Dataset description

This dataset contains the complete historical radiation-measurement snapshot published by Safecast. Safecast is a volunteer-driven citizen-science project created in 2011. Measurements are contributed by mobile and fixed devices and cover locations around the world.

The dataset supports environmental research, time-series analysis, mapping, sensor comparison, and studies of citizen-science data collection. Measurements should not be interpreted as official safety guidance or as a uniform spatial sample.

## Data structure

Each row represents one measurement. The `measurements` configuration contains:

| Field | Description |
| --- | --- |
| `captured_at` | Time recorded by the measuring device |
| `latitude`, `longitude` | WGS84 coordinates |
| `value`, `unit` | Reported measurement and its source unit |
| `location_name` | Optional location label |
| `device_id` | Safecast device identifier |
| `md5sum` | Source record checksum when supplied |
| `height` | Measurement height when supplied |
| `surface` | Surface description when supplied |
| `radiation` | Radiation metadata supplied by the source |
| `uploaded_at` | Time the record was uploaded |
| `loader_id` | Source loader identifier |

The original units are retained. Values with different units must not be compared without an appropriate conversion and knowledge of the detector involved.

## Processing

The official compressed CSV dump is read as a stream, assigned explicit Arrow types, divided into one-million-row shards, and stored as Zstandard-compressed Parquet. No API queries, interpolation, aggregation, unit conversion, or deduplication are applied. Provenance, schema, profile, quality, and checksum artifacts describe the exact snapshot.

## Data quality and limitations

Safecast is crowdsourced observational data. Geographic and temporal coverage is uneven, devices and collection protocols can differ, and optional metadata is frequently absent. Coordinates indicate reported measurement locations, not complete area coverage. Users should account for repeated measurements, device effects, sampling density, and source units in downstream analysis.

The published snapshot retains source anomalies rather than silently deleting them. It contains 29,707 rows without a captured time, 4,365 rows without coordinates, 229 captured times before 1900, and 33,063 captured times after the snapshot date. These rows can be filtered using `captured_at`, `latitude`, and `longitude` when a downstream task requires plausible time and location values.

All rows use the `train` split. Spatial or temporal evaluation splits should be created downstream to avoid leakage.

## Licence

Safecast publishes its measurement data under CC0 1.0. Attribution is not legally required, but acknowledging Safecast and its contributors is recommended.

Suggested attribution: `Source: Safecast contributors; transformed to Parquet.`
