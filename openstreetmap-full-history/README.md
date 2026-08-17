# OpenStreetMap full-history pipeline

This repository acquires a fixed OpenStreetMap full-history PBF snapshot. It contains historical versions of nodes, ways, and relations, including visible and deleted versions available in the public history dump.

The configured file is `history-260810.osm.pbf`, observed on 16 August 2026, with 161,613,547,811 bytes. No account or API key is required.

    powershell -ExecutionPolicy Bypass -File scripts/download.ps1
    powershell -ExecutionPolicy Bypass -File scripts/status.ps1
    python scripts/prepare.py

The PBF is never expanded to XML. Preparation requires a history-aware OSM reader and writes separate version, tag, node-reference, and relation-member tables in bounded shards.
