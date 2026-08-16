from __future__ import annotations

import zipfile
from pathlib import Path

from . import process as pipeline
from .processing_runner import read_batches


def valid_zip(path: Path) -> bool:
    """Validate the ZIP directory without decompressing CSV data a second time."""
    try:
        with zipfile.ZipFile(path) as archive:
            members = [
                info
                for info in archive.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".csv")
            ]
            return bool(members) and all(info.file_size > 0 for info in members)
    except (OSError, zipfile.BadZipFile):
        return False


def main() -> int:
    pipeline.read_batches = read_batches
    pipeline.valid_zip = valid_zip
    return pipeline.main()


if __name__ == "__main__":
    raise SystemExit(main())
