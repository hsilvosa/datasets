# GDELT Events historical pipeline

This directory contains a reproducible downloader for a fixed snapshot of the complete GDELT 1.0 Event Database. The default snapshot contains annual archives from 1979 through 2005, monthly archives from January 2006 through March 2013, and daily archives from 1 April 2013 through 14 August 2026.

The reduced 1979–2013 file is deliberately excluded because it aggregates events and duplicates part of the complete collection. GKG, Mentions, and GDELT 2.0 are separate products and are not downloaded.

```powershell
python -m gdelt_events estimate --config configs/default.json
python -m gdelt_events download --config configs/default.json
python -m gdelt_events verify --config configs/default.json
```

Downloads are resumable and concurrent. A completed archive is accepted only when its byte size and MD5 match the official GDELT manifests and the ZIP contains a tab-delimited event file. Partial files use the `.part` suffix. Running the command again verifies existing files and downloads only missing or invalid archives.

Raw source archives and their immutable manifests are stored under `data/full/raw`. The acquisition report and machine-readable provenance are stored under `artifacts`. No API key is required.

The GDELT file host is accessed over HTTP because its HTTPS certificate is not valid for the hostname on Windows. Published MD5 values protect against accidental corruption; SHA-256 values are also recorded locally after download.
