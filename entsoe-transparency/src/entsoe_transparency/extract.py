from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from .client import EntsoeClient, RateLimiter, inspect_response, load_token
from .config import Config
from .io_utils import atomic_bytes, atomic_json
from .tasks import DownloadTask, build_tasks


def _cached_status(path: Path) -> str | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return inspect_response(path.read_bytes()).status
    except Exception:  # noqa: BLE001 - any invalid cached response must be downloaded again
        return None


def _eta(started: float, completed: int, total: int) -> str:
    if completed == 0:
        return "unknown"
    remaining_seconds = (time.monotonic() - started) / completed * (total - completed)
    return f"{remaining_seconds / 3600:.2f}h"


def download(config: Config) -> dict[str, object]:
    token = load_token(config.token_env, config.env_file)
    tasks = build_tasks(config)
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = config.raw_dir / "download_manifest.json"
    existing: dict[str, dict[str, object]] = {}
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        existing = {item["task_id"]: item for item in payload.get("tasks", [])}

    pending: list[DownloadTask] = []
    manifest: dict[str, dict[str, object]] = {}
    cached = 0
    for task in tasks:
        status = _cached_status(task.path)
        if status:
            item = task.public_dict(config.raw_dir)
            item.update({"status": status, "bytes": task.path.stat().st_size, "cached": True})
            manifest[task.task_id] = item
            cached += 1
        else:
            pending.append(task)
            if task.task_id in existing:
                manifest[task.task_id] = existing[task.task_id]

    limiter = RateLimiter(config.requests_per_second)
    client = EntsoeClient(
        config.base_url,
        token,
        config.timeout_seconds,
        config.max_retries,
        config.user_agent,
        limiter,
    )
    lock = threading.Lock()
    failures: list[dict[str, str]] = []
    started = time.monotonic()
    total = len(pending)
    print(
        f"ENTSO-E download: {len(tasks)} tasks, {cached} cached, {total} pending, "
        f"{config.max_workers} workers",
        flush=True,
    )

    def fetch(task: DownloadTask) -> tuple[DownloadTask, str, int]:
        response = client.get(task.parameters())
        atomic_bytes(task.path, response.content)
        return task, response.status, len(response.content)

    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        futures = {executor.submit(fetch, task): task for task in pending}
        for completed, future in enumerate(as_completed(futures), start=1):
            task = futures[future]
            try:
                task, status, size = future.result()
                item = task.public_dict(config.raw_dir)
                item.update(
                    {
                        "status": status,
                        "bytes": size,
                        "cached": False,
                        "retrieved_at_utc": datetime.now(UTC).isoformat(),
                    }
                )
                with lock:
                    manifest[task.task_id] = item
            except Exception as exc:  # noqa: BLE001 - collect task errors and finish the queue
                failure = {"task_id": task.task_id, "error": str(exc)}
                failures.append(failure)
                print(f"FAILED {task.task_id}: {exc}", flush=True)
            if completed == 1 or completed % 25 == 0 or completed == total:
                elapsed = time.monotonic() - started
                bytes_now = sum(int(item.get("bytes", 0)) for item in manifest.values())
                print(
                    f"Progress {completed}/{total} new; elapsed {elapsed / 60:.1f}m; "
                    f"ETA {_eta(started, completed, total)}; raw {bytes_now / 1e9:.3f} GB",
                    flush=True,
                )
                atomic_json(
                    manifest_path,
                    {
                        "generated_at_utc": datetime.now(UTC).isoformat(),
                        "source": config.base_url,
                        "tasks": sorted(manifest.values(), key=lambda item: item["task_id"]),
                        "failures": failures,
                    },
                )

    duration = time.monotonic() - started
    values = list(manifest.values())
    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": config.base_url,
        "configured_tasks": len(tasks),
        "cached_tasks": cached,
        "downloaded_tasks": len(pending) - len(failures),
        "data_tasks": sum(item.get("status") == "data" for item in values),
        "no_data_tasks": sum(item.get("status") == "no_data" for item in values),
        "failed_tasks": len(failures),
        "response_bytes": sum(int(item.get("bytes", 0)) for item in values),
        "elapsed_seconds": round(duration, 3),
        "workers": config.max_workers,
        "requests_per_second": config.requests_per_second,
        "failures": failures,
    }
    atomic_json(config.raw_dir / "download_summary.json", summary)
    if failures:
        raise RuntimeError(f"{len(failures)} ENTSO-E tasks failed; rerun to resume")
    return summary
