# Processing GDELT Events

The processing configuration is separate from the immutable acquisition configuration. It records the two files listed by GDELT but unavailable from its server and the current server MD5 for the valid 22 March 2023 archive.

```powershell
python -m gdelt_events.process verify --config configs/processing.json
python -m gdelt_events.process normalize --config configs/processing.json
python -m gdelt_events.process analyze --config configs/processing.json
python -m gdelt_events.process stage --config configs/processing.json
```

`run` executes all four operations. Normalization reads CSV members directly from the ZIP archives, converts the 57-column legacy and 58-column current layouts to one typed schema, adds `source_archive`, and writes Zstandard-compressed Parquet shards. Raw CSV files are never extracted to disk.
