from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyze import analyze
from .client import download
from .config import Config
from .io_utils import human_bytes
from .normalize import normalize
from .publish import stage, upload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the BNE Linked Data dataset")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("estimate", "download", "normalize", "analyze", "stage", "run"):
        child = subparsers.add_parser(command)
        child.add_argument("--config", default="configs/default.json")
    uploader = subparsers.add_parser("upload")
    uploader.add_argument("--config", default="configs/default.json")
    uploader.add_argument("--repo-id", required=True)
    return parser


def estimate(config: Config) -> dict[str, object]:
    download_bytes = sum(item.expected_bytes for item in config.collections)
    if download_bytes < 50_000_000:
        download_minutes = "1-5"
    elif download_bytes < 500_000_000:
        download_minutes = "1-10"
    else:
        download_minutes = "5-30"
    end_to_end = "under 10 minutes" if config.max_triples_per_collection else "1.5-3 hours"
    return {
        "snapshot_date": config.snapshot_date,
        "collections": [item.name for item in config.collections],
        "download_bytes": download_bytes,
        "download_size": human_bytes(download_bytes),
        "estimated_download_minutes": download_minutes,
        "estimated_end_to_end": end_to_end,
        "recommended_free_disk": "10 GiB",
        "max_triples_per_collection": config.max_triples_per_collection,
        "note": "Estimates assume the configured source host remains available.",
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = Config.load(Path(args.config))
    if args.command == "estimate":
        result = estimate(config)
    elif args.command == "download":
        result = download(config)
    elif args.command == "normalize":
        result = normalize(config)
    elif args.command == "analyze":
        result = analyze(config)
    elif args.command == "stage":
        result = {"staging_dir": str(stage(config))}
    elif args.command == "upload":
        upload(config, args.repo_id)
        result = {"uploaded_to": args.repo_id}
    else:
        result = {"download": download(config)}
        result["normalize"] = normalize(config)
        result["profile"] = analyze(config)
        result["staging_dir"] = str(stage(config))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0
