from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyze import analyze
from .config import Config
from .extract import download
from .normalize import normalize
from .publish import stage, upload
from .tasks import build_tasks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the ENTSO-E prices and load dataset")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("estimate", "download", "normalize", "analyze", "stage", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", default="configs/default.json")
    uploader = subparsers.add_parser("upload")
    uploader.add_argument("--config", default="configs/default.json")
    uploader.add_argument("--repo-id", required=True)
    return parser


def _estimate(config: Config) -> dict[str, object]:
    tasks = build_tasks(config)
    by_dataset = {name: sum(task.dataset == name for task in tasks) for name in config.datasets}
    return {
        "tasks": len(tasks),
        "tasks_by_dataset": by_dataset,
        "zones": len(config.zones()),
        "workers": config.max_workers,
        "date_range": [config.start_date, config.end_date],
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = Config.load(Path(args.config))
    if args.command == "estimate":
        result = _estimate(config)
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
