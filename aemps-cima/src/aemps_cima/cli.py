from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyze import analyze
from .config import Config
from .extract import download
from .normalize import normalize
from .publish import stage, upload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the AEMPS CIMA research dataset")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("download", "normalize", "analyze", "stage", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", default="configs/default.json")
    uploader = subparsers.add_parser("upload")
    uploader.add_argument("--config", default="configs/default.json")
    uploader.add_argument("--repo-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = Config.load(Path(args.config))
    if args.command == "download":
        result = download(config)
    elif args.command == "normalize":
        result = normalize(config)
    elif args.command == "analyze":
        profile = analyze(config)
        result = {
            "artifacts_dir": str(config.artifacts_dir),
            "tables": {name: details["row_count"] for name, details in profile["tables"].items()},
        }
    elif args.command == "stage":
        result = {"staging_dir": str(stage(config))}
    elif args.command == "upload":
        upload(config, args.repo_id)
        result = {"uploaded_to": args.repo_id}
    else:
        result = {"download": download(config)}
        result["normalize"] = normalize(config)
        profile = analyze(config)
        result["profile"] = {
            name: details["row_count"] for name, details in profile["tables"].items()
        }
        result["staging_dir"] = str(stage(config))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
