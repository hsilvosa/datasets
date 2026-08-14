# Spanish Cadastre INSPIRE pipeline

Reproducible pipeline that downloads the Spanish Directorate-General for Cadastre INSPIRE bulk archives and converts their GML features to queryable GeoParquet tables.

The default configuration covers cadastral parcels, addresses, and buildings in the common-regime territory managed by the Directorate-General for Cadastre. Basque Country and Navarre foral cadastres are outside this release because they are published through separate systems.

## Commands

```powershell
python -m spanish_cadastre estimate --config configs/default.json
python -m spanish_cadastre run --config configs/sample.json
python -m spanish_cadastre download --config configs/default.json
python -m spanish_cadastre normalize --config configs/default.json
python -m spanish_cadastre analyze --config configs/default.json
python -m spanish_cadastre stage --config configs/default.json
```

`run` performs download, normalization, analysis, and staging. Downloads are resumable. Raw ZIP and GML files stay under `data/raw` and are excluded from the Hugging Face staging directory because the source licence permits publication of transformed products, not unchanged republication of the original files.

## Output

The processed directory contains one directory per table. Geometries use WKB in EPSG:4326 and include GeoParquet metadata and bounding-box columns. `artifacts` contains schemas, profiles, checksums, quality results, and provenance. `hf_staging` contains only the files intended for publication.

No API key is required.
