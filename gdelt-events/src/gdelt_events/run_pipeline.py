from __future__ import annotations

from typing import Any

from . import process as pipeline
from .full_runner import valid_zip
from .processing_runner import read_batches

_selected_archives = pipeline.selected_archives


def selected_archives(config: pipeline.ProcessingConfig) -> list[dict[str, Any]]:
    """Use current server object sizes for archives with documented checksum overrides."""
    archives = _selected_archives(config)
    for item in archives:
        if item["name"] in config.md5_overrides:
            item["published_bytes"] = item["bytes"]
            item["bytes"] = (config.raw_dir / item["name"]).stat().st_size
            item["size_source"] = "current server object Content-Length"
        else:
            item["size_source"] = "GDELT filesizes manifest"
    return archives


def main() -> int:
    pipeline.read_batches = read_batches
    pipeline.valid_zip = valid_zip
    pipeline.selected_archives = selected_archives
    return pipeline.main()


if __name__ == "__main__":
    raise SystemExit(main())
