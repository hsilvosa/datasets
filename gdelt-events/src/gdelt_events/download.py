from __future__ import annotations

import random
import threading
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .io_utils import atomic_json, file_hash
from .manifest import Archive, build_manifest


def valid_zip(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            return archive.testzip() is None and any(name.lower().endswith(".csv") for name in members)
    except (OSError, zipfile.BadZipFile):
        return False


def verify_archive(path: Path, archive: Archive, chunk_size: int) -> bool:
    return (
        path.exists()
        and path.stat().st_size == archive.size
        and file_hash(path, "md5", chunk_size) == archive.md5
        and valid_zip(path)
    )


def download_archive(archive: Archive, config: Config) -> dict[str, str | int | bool]:
    target = config.raw_dir / archive.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if verify_archive(target, archive, config.chunk_size):
        return {**archive.public_dict(), "cached": True, "sha256": file_hash(target, "sha256")}
    target.unlink(missing_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    url = f"{config.base_url}/{archive.name}"
    for attempt in range(config.max_retries + 1):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": config.user_agent, "Accept": "application/zip"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                append = offset > 0 and getattr(response, "status", None) == 206
                if offset and not append:
                    partial.unlink(missing_ok=True)
                mode = "ab" if append else "wb"
                with partial.open(mode) as handle:
                    while chunk := response.read(config.chunk_size):
                        handle.write(chunk)
            if partial.stat().st_size != archive.size:
                raise RuntimeError(f"size mismatch for {archive.name}")
            if file_hash(partial, "md5", config.chunk_size) != archive.md5:
                raise RuntimeError(f"MD5 mismatch for {archive.name}")
            partial.replace(target)
            if not valid_zip(target):
                target.replace(partial)
                raise RuntimeError(f"invalid ZIP structure for {archive.name}")
            return {
                **archive.public_dict(),
                "cached": False,
                "sha256": file_hash(target, "sha256"),
            }
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, RuntimeError):
            if attempt >= config.max_retries:
                raise
            time.sleep(min(30.0, 2**attempt + random.random()))
    raise AssertionError("unreachable")


def acquire_manifest(config: Config) -> tuple[list[Archive], str, str]:
    archives, md5_text, sizes_text = build_manifest(config)
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    (config.raw_dir / "source_md5sums.txt").write_text(md5_text, encoding="ascii")
    (config.raw_dir / "source_filesizes.txt").write_text(sizes_text, encoding="ascii")
    atomic_json(
        config.raw_dir / "snapshot_manifest.json",
        {
            "snapshot_date": config.snapshot_date.isoformat(),
            "archives": [archive.public_dict() for archive in archives],
        },
    )
    return archives, md5_text, sizes_text


def estimate(config: Config) -> dict[str, object]:
    archives, _, _ = acquire_manifest(config)
    return {
        "snapshot_date": config.snapshot_date.isoformat(),
        "archives": len(archives),
        "compressed_bytes": sum(archive.size for archive in archives),
        "first_period": archives[0].period,
        "last_period": archives[-1].period,
    }


def download(config: Config) -> dict[str, object]:
    archives, _, _ = acquire_manifest(config)
    started = datetime.now(UTC)
    lock = threading.Lock()
    completed = 0
    results: list[dict[str, str | int | bool]] = []
    with ThreadPoolExecutor(max_workers=config.workers) as executor:
        futures = {executor.submit(download_archive, archive, config): archive for archive in archives}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            with lock:
                completed += 1
                if completed == 1 or completed % 25 == 0 or completed == len(archives):
                    print(
                        f"GDELT download {completed}/{len(archives)}: {result['name']}",
                        flush=True,
                    )
    results.sort(key=lambda item: str(item["period"]))
    summary = {
        "publisher": "The GDELT Project",
        "product": "GDELT 1.0 Event Database",
        "snapshot_date": config.snapshot_date.isoformat(),
        "started_at_utc": started.isoformat(),
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "archives": len(results),
        "cached_archives": sum(bool(item["cached"]) for item in results),
        "compressed_bytes": sum(int(item["bytes"]) for item in results),
        "files": results,
    }
    atomic_json(config.raw_dir / "download_summary.json", summary)
    atomic_json(config.artifacts_dir / "provenance.json", summary)
    return {key: value for key, value in summary.items() if key != "files"}


def verify(config: Config) -> dict[str, object]:
    archives, _, _ = acquire_manifest(config)
    invalid = [
        archive.name
        for archive in archives
        if not verify_archive(config.raw_dir / archive.name, archive, config.chunk_size)
    ]
    result = {
        "snapshot_date": config.snapshot_date.isoformat(),
        "expected_archives": len(archives),
        "valid_archives": len(archives) - len(invalid),
        "invalid_or_missing": invalid,
        "verified_at_utc": datetime.now(UTC).isoformat(),
    }
    atomic_json(config.artifacts_dir / "quality.json", result)
    return result
