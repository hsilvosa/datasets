from __future__ import annotations

import argparse
import json
from typing import Any

from .analyze import coverage_summary, run_analyze
from .config import Config
from .extract import run_download
from .io_utils import read_json
from .normalize import run_normalize
from .publish import stage


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Resumable, append-only extractor for the Spanish BOE and BORME open data"
    )
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("download", "normalize", "analyze", "stage", "run", "status"):
        command = commands.add_parser(name)
        command.add_argument("--config", default="configs/default.json")
    return result


def _status(config: Config) -> dict[str, Any]:
    state = config.state_dir
    output: dict[str, Any] = {
        "end_date": config.resolved_end_date,
        "coverage": coverage_summary(config),
    }
    for name in ("last_download.json", "last_normalize.json"):
        path = state / name
        if path.exists():
            output[name.removesuffix(".json")] = read_json(path)
    quality_path = config.artifacts_dir / "quality.json"
    if quality_path.exists():
        output["quality_status"] = read_json(quality_path).get("status")
    return output


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = Config.load(args.config)
    if args.command == "download":
        output: dict[str, Any] = run_download(config)
    elif args.command == "normalize":
        output = run_normalize(config)
    elif args.command == "analyze":
        profile = run_analyze(config)
        output = {"artifacts_dir": str(config.artifacts_dir), "total_rows": profile["total_rows"]}
    elif args.command == "stage":
        output = {"staging_dir": str(stage(config))}
    elif args.command == "status":
        output = _status(config)
    else:
        download = run_download(config)
        if download["errors"]:
            print(
                json.dumps({"download": download, "aborted": "download errors"}, indent=2)
            )
            return 1
        normalize = run_normalize(config)
        profile = run_analyze(config)
        quality = read_json(config.artifacts_dir / "quality.json")
        if quality.get("status") != "pass":
            print(
                json.dumps(
                    {
                        "download": download,
                        "normalize": normalize,
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
            "download": download,
            "normalize": normalize,
            "analyze": {"total_rows": profile["total_rows"]},
            "staging_dir": str(stage(config)),
        }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0
