from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyze import analyze
from .catalog import discover
from .config import Config
from .extract import download
from .normalize import normalize
from .publish import stage, upload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build the Spanish Cadastre INSPIRE dataset")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("estimate", "download", "normalize", "analyze", "stage", "run"):
        command = commands.add_parser(name)
        command.add_argument("--config", default="configs/default.json")
    uploader = commands.add_parser("upload")
    uploader.add_argument("--config", default="configs/default.json")
    uploader.add_argument("--repo-id", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = Config.load(Path(args.config))
    if args.command == "estimate":
        tasks = discover(config)
        output = {
            "municipalities": len({task.municipality_code for task in tasks}),
            "archives": len(tasks),
            "archives_by_collection": {
                name: sum(task.collection == name for task in tasks) for name in config.collections
            },
        }
    elif args.command == "download":
        output = download(config)
    elif args.command == "normalize":
        output = normalize(config)
    elif args.command == "analyze":
        output = analyze(config)
    elif args.command == "stage":
        output = {"staging_dir": str(stage(config))}
    elif args.command == "upload":
        upload(config, args.repo_id)
        output = {"uploaded_to": args.repo_id}
    else:
        output = {"download": download(config)}
        output["normalize"] = normalize(config)
        output["profile"] = analyze(config)
        output["staging_dir"] = str(stage(config))
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0
