# Open Food Facts historical snapshot

This repository downloads and prepares a dated Open Food Facts product snapshot. The JSONL dump is selected because it preserves substantially more fields than the flattened CSV export.

The configured snapshot was observed on 16 August 2026 and is 12,682,967,056 bytes compressed. No API key is required.

    powershell -ExecutionPolicy Bypass -File scripts/download.ps1
    powershell -ExecutionPolicy Bypass -File scripts/status.ps1
    python scripts/prepare.py

The download resumes from a `.part` file. Normalization will stream gzip JSON lines into Parquet shards and retain nested fields as JSON where a stable tabular representation would lose information.
