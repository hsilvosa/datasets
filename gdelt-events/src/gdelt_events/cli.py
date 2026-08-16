from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Config
from .download import download, estimate, verify


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Acquire the historical GDELT Event Database")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("estimate", "download", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--config", default="configs/default.json")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = Config.load(Path(args.config))
    if args.command == "estimate":
        output = estimate(config)
    elif args.command == "download":
        output = download(config)
    else:
        output = verify(config)
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0
