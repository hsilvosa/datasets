from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyze import analyze
from .config import Config
from .normalize import normalize
from .publish import stage, upload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Safecast historical dataset")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("normalize", "analyze", "stage", "run"):
        command = commands.add_parser(name)
        command.add_argument("--config", default="configs/default.json")
    uploader = commands.add_parser("upload")
    uploader.add_argument("--config", default="configs/default.json")
    uploader.add_argument("--repo-id", required=True)
    args = parser.parse_args(argv)
    config = Config.load(Path(args.config))
    if args.command == "normalize":
        output = normalize(config)
    elif args.command == "analyze":
        output = analyze(config)
    elif args.command == "stage":
        output = {"staging_dir": str(stage(config))}
    elif args.command == "upload":
        upload(config, args.repo_id)
        output = {"uploaded_to": args.repo_id}
    else:
        output = {"normalize": normalize(config)}
        output["profile"] = analyze(config)
        output["staging_dir"] = str(stage(config))
    print(json.dumps(output, indent=2, default=str))
    return 0
