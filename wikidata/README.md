# Wikidata historical snapshot

This repository acquires and prepares a dated Wikidata entity dump. The complete JSON bzip2 dump is retained as the authoritative raw input.

The configured entity snapshot is dated 10 August 2026, was published on 12 August, and is 102,674,245,605 bytes compressed. The URL is dated and immutable; the official MD5 and SHA-1 values are recorded in the configuration. No account or API key is required.

    powershell -ExecutionPolicy Bypass -File scripts/download.ps1
    powershell -ExecutionPolicy Bypass -File scripts/status.ps1
    python scripts/prepare.py

Preparation streams bzip2 input and writes sharded entity, label, description, alias, sitelink, and claim tables. It does not materialize the uncompressed JSON dump on disk.
