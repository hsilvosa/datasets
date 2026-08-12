from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .config import Config, Zone


@dataclass(frozen=True)
class DownloadTask:
    dataset: str
    zone: Zone
    start: date
    end: date
    path: Path

    @property
    def task_id(self) -> str:
        return f"{self.dataset}:{self.zone.key}:{self.start}:{self.end}"

    def parameters(self) -> dict[str, str]:
        common = {
            "periodStart": self.start.strftime("%Y%m%d0000"),
            "periodEnd": self.end.strftime("%Y%m%d0000"),
        }
        if self.dataset == "day_ahead_prices":
            return {
                **common,
                "documentType": "A44",
                "in_Domain": self.zone.eic_code,
                "out_Domain": self.zone.eic_code,
            }
        return {
            **common,
            "documentType": "A65",
            "processType": "A16",
            "outBiddingZone_Domain": self.zone.eic_code,
        }

    def public_dict(self, root: Path) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "dataset": self.dataset,
            "zone": asdict(self.zone),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "file": self.path.relative_to(root).as_posix(),
        }


def add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_zero = divmod(month_index, 12)
    return date(year, month_zero + 1, 1)


def _periods(start: date, end: date, months: int):
    cursor = start
    while cursor < end:
        following = min(add_months(cursor, months), end)
        yield cursor, following
        cursor = following


def build_tasks(config: Config) -> list[DownloadTask]:
    configured_start = date.fromisoformat(config.start_date)
    configured_end = date.fromisoformat(config.end_date)
    tasks: list[DownloadTask] = []
    for zone in config.zones():
        zone_start = max(
            configured_start,
            date.fromisoformat(zone.valid_from) if zone.valid_from else configured_start,
        )
        zone_end = min(
            configured_end,
            date.fromisoformat(zone.valid_to) if zone.valid_to else configured_end,
        )
        if zone_start >= zone_end:
            continue
        for dataset in config.datasets:
            months = (
                config.price_chunk_months
                if dataset == "day_ahead_prices"
                else config.load_chunk_months
            )
            for start, end in _periods(zone_start, zone_end, months):
                filename = f"{zone.key}_{start:%Y%m%d}_{end:%Y%m%d}.xml"
                tasks.append(
                    DownloadTask(
                        dataset=dataset,
                        zone=zone,
                        start=start,
                        end=end,
                        path=config.raw_dir / dataset / filename,
                    )
                )
    tasks.sort(key=lambda item: (item.dataset, item.start, item.zone.key))
    return tasks[: config.max_tasks] if config.max_tasks is not None else tasks
