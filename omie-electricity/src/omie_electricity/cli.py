from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .analyze import generate_metadata
from .config import Config
from .extract import extract
from .normalize import normalize
from .publish import publish, stage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("omie_electricity")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omie-electricity",
        description="Pipeline for OMIE Iberian electricity market data",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "download", "normalize", "analyze", "stage", "run", "all"):
        sub = commands.add_parser(name)
        sub.add_argument(
            "--config",
            type=Path,
            default=Path("configs/default.json"),
            help="Path to JSON configuration file",
        )

    pub = commands.add_parser("publish")
    pub.add_argument("--config", type=Path, default=Path("configs/default.json"))
    pub.add_argument("--repo-id", required=True, help="Hugging Face repository ID (e.g. user/dataset)")
    pub.add_argument("--token", help="Hugging Face API token")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = Config.load(args.config)

    output = {}
    if args.command in ("extract", "download"):
        output["extract"] = extract(config)
    elif args.command == "normalize":
        output["normalize"] = normalize(config)
    elif args.command == "analyze":
        output["analyze"] = generate_metadata(config)
    elif args.command == "stage":
        staging_path = stage(config)
        output["stage"] = {"staging_dir": str(staging_path)}
    elif args.command == "publish":
        publish(config, repo_id=args.repo_id, token=args.token)
        output["publish"] = {"status": "success", "repo_id": args.repo_id}
    else:  # run or all
        output["extract"] = extract(config)
        output["normalize"] = normalize(config)
        output["analyze"] = generate_metadata(config)
        staging_path = stage(config)
        output["stage"] = {"staging_dir": str(staging_path)}

    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
