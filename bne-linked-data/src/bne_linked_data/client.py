from __future__ import annotations

import json
import re
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import Collection, Config


class DownloadError(RuntimeError):
    """Raised when a source file cannot be downloaded safely."""


@dataclass(frozen=True)
class DownloadResult:
    collection: str
    path: str
    bytes: int
    resumed_from: int
    elapsed_seconds: float
    status: str


def _validate_source(path, collection: Collection) -> None:
    if path.stat().st_size == 0:
        raise DownloadError(f"{collection.name}: source file is empty: {path}")
    if collection.filename.endswith(".bz2"):
        with path.open("rb") as handle:
            if handle.read(3) != b"BZh":
                raise DownloadError(
                    f"{collection.name}: {path} is not a BZip2 file; it may be an HTML block page"
                )


def _request(url: str, start: int, timeout: int):
    headers = {
        "Accept": "application/octet-stream,*/*",
        "User-Agent": "bne-linked-data-pipeline/0.1 (+https://www.bne.es/)",
    }
    if start:
        headers["Range"] = f"bytes={start}-"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)


def download_one(config: Config, collection: Collection) -> DownloadResult:
    destination = config.raw_path(collection)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        _validate_source(destination, collection)
        return DownloadResult(
            collection.name,
            str(destination),
            destination.stat().st_size,
            destination.stat().st_size,
            0.0,
            "already_complete",
        )
    if collection.local_path:
        source = config.project_root / collection.local_path
        if not source.exists():
            raise DownloadError(f"{collection.name}: missing local fixture {source}")
        started = time.perf_counter()
        shutil.copy2(source, destination)
        _validate_source(destination, collection)
        return DownloadResult(
            collection.name,
            str(destination),
            destination.stat().st_size,
            0,
            round(time.perf_counter() - started, 3),
            "copied_fixture",
        )
    partial = destination.with_suffix(destination.suffix + ".part")
    started = time.perf_counter()
    last_error: Exception | None = None
    for attempt in range(config.retries):
        existing = partial.stat().st_size if partial.exists() else 0
        try:
            with _request(collection.url, existing, config.timeout_seconds) as response:
                code = getattr(response, "status", response.getcode())
                if existing and code != 206:
                    partial.unlink(missing_ok=True)
                    existing = 0
                content_range = response.headers.get("Content-Range", "")
                match = re.search(r"/(\d+)$", content_range)
                if match:
                    remote_total = int(match.group(1))
                else:
                    length = response.headers.get("Content-Length")
                    remote_total = existing + int(length) if length else None
                mode = "ab" if existing and code == 206 else "wb"
                with partial.open(mode) as target:
                    while block := response.read(1024 * 1024):
                        target.write(block)
            size = partial.stat().st_size
            if remote_total is not None and size != remote_total:
                raise DownloadError(
                    f"{collection.name}: server announced {remote_total} bytes, received {size}"
                )
            _validate_source(partial, collection)
            partial.replace(destination)
            return DownloadResult(
                collection.name,
                str(destination),
                size,
                existing,
                round(time.perf_counter() - started, 3),
                "downloaded",
            )
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 403:
                raise DownloadError(
                    f"{collection.name}: source returned HTTP 403. The BNE Cloudflare rule "
                    "currently blocks automated access; retry from an allowed network or use an "
                    "official mirror URL in the configuration."
                ) from exc
        except (OSError, urllib.error.URLError, DownloadError) as exc:
            last_error = exc
        if attempt + 1 < config.retries:
            time.sleep(min(2**attempt, 20))
    raise DownloadError(f"{collection.name}: download failed after {config.retries} attempts") from last_error


def download(config: Config) -> dict[str, object]:
    results = [download_one(config, item) for item in config.collections]
    payload = {
        "snapshot_date": config.snapshot_date,
        "collections": [result.__dict__ for result in results],
        "total_bytes": sum(result.bytes for result in results),
    }
    manifest = config.raw_dir / "download_manifest.json"
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
