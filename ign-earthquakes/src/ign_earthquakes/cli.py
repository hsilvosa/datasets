from __future__ import annotations

import argparse
import json

from .analyze import analyze
from .config import Config
from .extract import download
from .normalize import normalize
from .publish import stage


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Extract a small IGN earthquake catalogue sample")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("download", "normalize", "analyze", "stage", "run"):
        command = commands.add_parser(name)
        command.add_argument("--config", default="configs/sample.json")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = Config.load(args.config)
    if args.command == "download":
        output = download(config)
    elif args.command == "normalize":
        output = normalize(config)
    elif args.command == "analyze":
        profile = analyze(config)
        output = {
            "artifacts_dir": str(config.artifacts_dir),
            "rows": profile["tables"]["earthquakes"]["row_count"],
        }
    elif args.command == "stage":
        output = {"staging_dir": str(stage(config))}
    else:
        output = {"download": download(config), "normalize": normalize(config)}
        profile = analyze(config)
        output["profile"] = {"rows": profile["tables"]["earthquakes"]["row_count"]}
        output["staging_dir"] = str(stage(config))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0
