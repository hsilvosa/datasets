from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from .client import OMIEClient
from .config import Config

logger = logging.getLogger(__name__)


def daterange(start_date: date, end_date: date):
    curr = start_date
    while curr <= end_date:
        yield curr
        curr += timedelta(days=1)


def extract(config: Config) -> dict[str, int]:
    """Download daily OMIE marginal prices and bidding curves."""
    client = OMIEClient(
        user_agent=config.user_agent,
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
        delay=config.request_delay_seconds,
    )

    config.raw_dir.mkdir(parents=True, exist_ok=True)

    marginal_downloaded = 0
    marginal_skipped = 0
    curves_downloaded = 0
    curves_skipped = 0

    for day in daterange(config.parsed_start_date, config.parsed_end_date):
        year_dir = config.raw_dir / str(day.year)
        year_dir.mkdir(parents=True, exist_ok=True)
        date_str = day.strftime("%Y%m%d")

        # 1. Marginal price file
        marginal_file = year_dir / f"marginalpdbc_{date_str}.1"
        if marginal_file.exists() and marginal_file.stat().st_size > 0:
            marginal_skipped += 1
        else:
            data = client.fetch_marginalpdbc(day)
            if data:
                marginal_file.write_bytes(data)
                marginal_downloaded += 1

        # 2. Bidding curve file
        if config.include_curves:
            curve_file = year_dir / f"curva_pbc_{date_str}.1"
            if curve_file.exists() and curve_file.stat().st_size > 0:
                curves_skipped += 1
            else:
                cdata = client.fetch_curva_pbc(day)
                if cdata:
                    curve_file.write_bytes(cdata)
                    curves_downloaded += 1
                    logger.info("Saved curve %s (%d KB)", curve_file.name, len(cdata) // 1024)

    stats = {
        "marginal_downloaded": marginal_downloaded,
        "marginal_skipped": marginal_skipped,
        "curves_downloaded": curves_downloaded,
        "curves_skipped": curves_skipped,
    }
    logger.info("OMIE extraction summary: %s", stats)
    return stats
