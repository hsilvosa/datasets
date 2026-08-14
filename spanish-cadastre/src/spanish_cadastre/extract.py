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

from .catalog import DownloadTask, discover
from .config import Config
from .io_utils import atomic_json, sha256_file


def valid_zip(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            return archive.testzip() is None and any(
                name.lower().endswith(".gml") for name in archive.namelist()
            )
    except zipfile.BadZipFile:
        return False


class RateLimiter:
    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.lock = threading.Lock()
        self.last_request = 0.0

    def wait(self) -> None:
        with self.lock:
            remaining = self.delay - (time.monotonic() - self.last_request)
            if remaining > 0:
                time.sleep(remaining)
            self.last_request = time.monotonic()


def download_task(task: DownloadTask, config: Config, limiter: RateLimiter) -> None:
    task.path.parent.mkdir(parents=True, exist_ok=True)
    partial = task.path.with_suffix(task.path.suffix + ".part")
    for attempt in range(config.max_retries + 1):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": config.user_agent}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            limiter.wait()
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
                raise RuntimeError(f"Invalid ZIP archive: {task.path.name}")
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, RuntimeError):
            if attempt >= config.max_retries:
                raise
            time.sleep(min(30.0, 2**attempt + random.random()))


def download(config: Config) -> dict[str, object]:
    tasks = discover(config)
    limiter = RateLimiter(config.request_delay_seconds)
    pending = [task for task in tasks if not valid_zip(task.path)]
    cached = len(tasks) - len(pending)
    failures: list[dict[str, str]] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        futures = {executor.submit(download_task, task, config, limiter): task for task in pending}
        for future in as_completed(futures):
            task = futures[future]
            try:
                future.result()
                completed += 1
                if completed % 25 == 0 or completed == len(pending):
                    print(f"Cadastre download {completed}/{len(pending)}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({"task_id": task.task_id, "error": type(exc).__name__})
    files = [
        {
            **task.public_dict(config.raw_dir),
            "bytes": task.path.stat().st_size,
            "sha256": sha256_file(task.path),
        }
        for task in tasks
        if valid_zip(task.path)
    ]
    summary = {
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "publisher": "Directorate-General for Cadastre",
        "tasks": len(tasks),
        "cached": cached,
        "downloaded": completed,
        "failures": failures,
        "files": files,
    }
    atomic_json(config.raw_dir / "download_summary.json", summary)
    if failures:
        raise RuntimeError(f"{len(failures)} Cadastre downloads failed")
    return summary
