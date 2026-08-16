# Safecast historical pipeline

This pipeline converts the complete Safecast radiation-measurement dump into typed, compressed Parquet shards. It reads the CSV directly from the TAR.GZ archive, so the 33 GB source CSV does not need to be extracted to disk.

The release is a fixed historical snapshot. It does not use streaming or periodically append new observations. No API key is required.

```powershell
python -m safecast_historical run --config configs/default.json
```

The source archive remains under `data/raw` and is excluded from the Hugging Face staging directory. Processed data is written under `data/processed`, validation and provenance under `artifacts`, and publishable files under `hf_staging`.
