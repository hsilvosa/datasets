from __future__ import annotations

import argparse
import json
from typing import Any

from .analyze import coverage, run_analyze
from .config import Config
from .derive import run_derive
from .io_utils import read_json
from .publish import stage


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Derived block- and version-level tables from the BOE/BORME release"
    )
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("derive", "analyze", "stage", "run", "status"):
        command = commands.add_parser(name)
        command.add_argument("--config", default="configs/default.json")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = Config.load(args.config)
    if args.command == "derive":
        output: dict[str, Any] = run_derive(config)
    elif args.command == "analyze":
        profile = run_analyze(config)
        output = {"artifacts_dir": str(config.artifacts_dir), "total_rows": profile["total_rows"]}
    elif args.command == "stage":
        output = {"staging_dir": str(stage(config))}
    elif args.command == "status":
        output = {"base_dataset": config.base_dataset, "coverage": coverage(config)}
        state_path = config.state_dir / "last_derive.json"
        if state_path.exists():
            output["last_derive"] = read_json(state_path)
    else:
        derive = run_derive(config)
        profile = run_analyze(config)
        quality = read_json(config.artifacts_dir / "quality.json")
        if quality.get("status") != "pass":
            print(
                json.dumps(
                    {
                        "derive": derive,
                        "analyze": {"total_rows": profile["total_rows"]},
                        "quality": quality,
                        "aborted": "quality status is not pass",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        output = {
            "derive": derive,
            "analyze": {"total_rows": profile["total_rows"]},
            "staging_dir": str(stage(config)),
        }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0
