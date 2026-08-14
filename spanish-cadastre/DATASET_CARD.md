# Spanish Cadastre INSPIRE

## Dataset description

Spanish Cadastre INSPIRE is a normalized snapshot of cadastral parcels, cadastral zoning, addresses, buildings, building parts, and other constructions published by Spain's Directorate-General for Cadastre. It is intended for geospatial analysis, spatial joins, address research, building-stock studies, and reproducible public-data workflows.

The dataset covers the common-regime cadastral territory managed by the Directorate-General for Cadastre. It does not include the foral cadastral systems of the Basque Country and Navarre.

## Data structure

Each table is exposed as a separate dataset configuration:

| Configuration | Unit of observation | Geometry |
| --- | --- | --- |
| `cadastral_parcels` | Cadastral parcel | Polygon or MultiPolygon |
| `cadastral_zonings` | Cadastral zoning area | Polygon or MultiPolygon |
| `addresses` | Address | Point |
| `buildings` | Building | Polygon or MultiPolygon |
| `building_parts` | Building part | Polygon or MultiPolygon |
| `other_constructions` | Other construction | Polygon or MultiPolygon |
| `municipalities` | Municipality and source archive index | None |

All spatial tables share stable feature and source fields: `feature_id`, `local_id`, `namespace`, province and municipality identifiers, lifespan timestamps, original CRS, WKB geometry, WGS84 bounding boxes, source archive and member names, and `properties_json`. The JSON field preserves source attributes that are not promoted to dedicated columns.

Parcel and zoning tables include area, label, national reference, accuracy, level, and source-scale fields when supplied. Addresses include locator and validity dates. Construction tables include condition, construction dates, current use, unit and dwelling counts, floor counts, official area, and references to parcels and addresses when supplied.

## Spatial representation

Source coordinates are transformed to EPSG:4326. Geometry is stored as WKB with GeoParquet 1.1 metadata. Bounding-box columns allow row-group filtering without decoding every geometry. The original coordinate reference system is retained in `source_crs`.

## Provenance and processing

The source consists of the INSPIRE bulk-download archives published by the Directorate-General for Cadastre. GML features are parsed, typed, reprojected, and written as compressed Parquet. Original archives are not included in this repository. The accompanying artifacts record the retrieval URLs, configuration, schemas, table profiles, checksums, and validation results for the exact published snapshot.

## Data quality

Cadastre records describe administrative source data rather than ground truth. Coverage and update dates can vary by municipality and feature type. Optional attributes may be absent. Users should inspect `artifacts/profile.json` and `artifacts/quality.json` for the row counts, bounds, null checks, and validation status of this snapshot.

## Splits

All rows use the `train` split. Geographic or temporal evaluation splits should be created downstream to prevent spatial leakage when the dataset is used for machine learning.

## Licence and attribution

The transformed dataset is distributed under the conditions of the Directorate-General for Cadastre data-access licence. Reuse must identify the Directorate-General for Cadastre as the source and must not imply that transformed results are official cadastral products. Consult the included provenance artifacts for the exact source files used.

Suggested attribution: `Source: Dirección General del Catastro, Spain; transformed to GeoParquet.`
