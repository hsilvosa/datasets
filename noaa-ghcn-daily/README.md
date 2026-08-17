# NOAA GHCN-Daily historical pipeline

This repository acquires a dated copy of NOAA Global Historical Climatology Network Daily. It retains the compressed station archive and the official station, inventory, country, state, version, and format metadata.

The configured snapshot was observed on 16 August 2026. The main archive is 3,710,978,683 bytes. No account or API key is required.

    powershell -ExecutionPolicy Bypass -File scripts/download.ps1
    powershell -ExecutionPolicy Bypass -File scripts/status.ps1
    python scripts/prepare.py

Downloads are resumable. Incomplete content uses a `.part` suffix. Raw data, generated artifacts, and Parquet files are excluded from Git.

Preparation will read `.dly` members directly from the tar.gz archive and write long-form Parquet shards without extracting the full archive.
