from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime

from .config import Config

YEARLY = re.compile(r"^(\d{4})\.zip$")
MONTHLY = re.compile(r"^(\d{6})\.zip$")
DAILY = re.compile(r"^(\d{8})\.export\.CSV\.zip$")


@dataclass(frozen=True)
class Archive:
    name: str
    size: int
    md5: str
    period: str

    def public_dict(self) -> dict[str, str | int]:
        return {"name": self.name, "period": self.period, "bytes": self.size, "md5": self.md5}


def fetch_text(url: str, config: Config) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": config.user_agent})
    with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
        return response.read().decode("ascii")


def parse_checksums(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{32}", parts[0]):
            result[parts[1]] = parts[0].lower()
    return result


def parse_sizes(text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit():
            result[parts[1]] = int(parts[0])
    return result


def archive_period(name: str, snapshot_date: date) -> str | None:
    if match := YEARLY.fullmatch(name):
        year = int(match.group(1))
        return str(year) if 1979 <= year <= 2005 else None
    if match := MONTHLY.fullmatch(name):
        value = match.group(1)
        parsed = datetime.strptime(value, "%Y%m").date()  # noqa: DTZ007
        return value if date(2006, 1, 1) <= parsed <= date(2013, 3, 1) else None
    if match := DAILY.fullmatch(name):
        value = match.group(1)
        parsed = datetime.strptime(value, "%Y%m%d").date()  # noqa: DTZ007
        return value if date(2013, 4, 1) <= parsed <= snapshot_date else None
    return None


def build_manifest(config: Config) -> tuple[list[Archive], str, str]:
    md5_text = fetch_text(f"{config.base_url}/md5sums", config)
    sizes_text = fetch_text(f"{config.base_url}/filesizes", config)
    checksums = parse_checksums(md5_text)
    sizes = parse_sizes(sizes_text)
    names = sorted(set(checksums) & set(sizes))
    archives = [
        Archive(name=name, size=sizes[name], md5=checksums[name], period=period)
        for name in names
        if (period := archive_period(name, config.snapshot_date)) is not None
    ]
    archives.sort(key=lambda item: item.period)
    if not archives:
        raise RuntimeError("The official manifests did not contain any matching archives")
    if config.max_files is not None:
        archives = archives[: config.max_files]
    return archives, md5_text, sizes_text
