from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config

BASE_URL = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643"
STEM = "licitacionesPerfilesContratanteCompleto3"


@dataclass(frozen=True)
class DownloadTask:
    period: str
    url: str
    path: Path

    def public_dict(self, root: Path) -> dict[str, str]:
        return {
            "period": self.period,
            "url": self.url,
            "file": self.path.relative_to(root).as_posix(),
        }


def build_tasks(config: Config) -> list[DownloadTask]:
    tasks: list[DownloadTask] = []
    for year in range(config.start_year, config.end_year + 1):
        if year < config.monthly_from_year:
            periods = [str(year)]
        else:
            last_month = config.end_month if year == config.end_year else 12
            periods = [f"{year}{month:02d}" for month in range(1, last_month + 1)]
        for period in periods:
            filename = f"{STEM}_{period}.zip"
            tasks.append(DownloadTask(period, f"{BASE_URL}/{filename}", config.raw_dir / filename))
    return tasks[: config.max_archives] if config.max_archives is not None else tasks
