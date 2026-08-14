from __future__ import annotations

import random
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .io_utils import atomic_json, sha256_file
from .tasks import DownloadTask, build_tasks


def valid_zip(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.namelist()
            return archive.testzip() is None and any(
                name.lower().endswith((".atom", ".xml")) for name in members
            )
    except zipfile.BadZipFile:
        return False


def download_task(task: DownloadTask, config: Config) -> None:
    task.path.parent.mkdir(parents=True, exist_ok=True)
    partial = task.path.with_suffix(task.path.suffix + ".part")
    for attempt in range(config.max_retries + 1):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": config.user_agent, "Accept": "application/zip"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            request = urllib.request.Request(task.url, headers=headers)
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                append = offset > 0 and getattr(response, "status", None) == 206
                if offset and not append:
                    partial.unlink(missing_ok=True)
                with partial.open("ab" if append else "wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
            partial.replace(task.path)
            if not valid_zip(task.path):
                task.path.replace(partial)
                raise RuntimeError(f"Downloaded archive is not a valid ZIP: {task.path.name}")
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, RuntimeError):
            if attempt >= config.max_retries:
                raise
            time.sleep(min(30.0, 2**attempt + random.random()))


def download(config: Config) -> dict[str, object]:
    tasks = build_tasks(config)
    cached = 0
    files: list[dict[str, object]] = []
    for index, task in enumerate(tasks, 1):
        if valid_zip(task.path):
            cached += 1
        else:
            print(f"OpenPLACSP download {index}/{len(tasks)}: {task.period}", flush=True)
            download_task(task, config)
        files.append(
            {
                **task.public_dict(config.raw_dir),
                "bytes": task.path.stat().st_size,
                "sha256": sha256_file(task.path),
            }
        )
    summary = {
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "publisher": "Plataforma de Contratacion del Sector Publico",
        "archives": len(tasks),
        "cached_archives": cached,
        "files": files,
    }
    atomic_json(config.raw_dir / "download_summary.json", summary)
    return summary
