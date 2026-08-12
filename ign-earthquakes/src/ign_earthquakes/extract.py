from __future__ import annotations

import calendar
from datetime import UTC, datetime

from .client import IgnClient
from .config import Config
from .io_utils import atomic_bytes, atomic_json


def query_from_config(config: Config) -> dict[str, str]:
    return {
        "fases": "no",
        "selIntensidad": "N",
        "selMagnitud": "N",
        "selProf": "N",
        "latMin": str(config.latitude_min),
        "latMax": str(config.latitude_max),
        "longMin": str(config.longitude_min),
        "longMax": str(config.longitude_max),
        "startDate": config.start_date,
        "endDate": config.end_date,
        "intMin": "",
        "intMax": "",
        "magMin": "",
        "magMax": "",
        "cond": "",
        "profMin": "",
        "profMax": "",
    }


def shard_queries(config: Config) -> list[tuple[str, dict[str, str]]]:
    base_query = query_from_config(config)
    if config.shard_years is None:
        return [("earthquakes.csv", base_query)]
    start = datetime.strptime(config.start_date, "%d/%m/%Y").replace(tzinfo=UTC)
    end = datetime.strptime(config.end_date, "%d/%m/%Y").replace(tzinfo=UTC)
    shards: list[tuple[str, dict[str, str]]] = []
    first_year = start.year
    if (
        config.coalesce_before_year is not None
        and first_year < config.coalesce_before_year
    ):
        last_year = min(config.coalesce_before_year - 1, end.year)
        shard_end = (
            end if last_year == end.year else datetime(last_year, 12, 31, tzinfo=UTC)
        )
        query = {
            **base_query,
            "startDate": start.strftime("%d/%m/%Y"),
            "endDate": shard_end.strftime("%d/%m/%Y"),
        }
        shards.append((f"earthquakes-{first_year:04d}-{last_year:04d}.csv", query))
        first_year = last_year + 1
    while first_year <= end.year:
        last_year = min(first_year + config.shard_years - 1, end.year)
        annual = any(
            first_year >= bounds[0] and last_year <= bounds[1]
            for bounds in (config.annual_shard_ranges or [])
        )
        if annual:
            for year in range(first_year, last_year + 1):
                if year in (config.monthly_shard_years or []):
                    for month in range(1, 13):
                        last_day = calendar.monthrange(year, month)[1]
                        if [year, month] in (config.daily_shard_months or []):
                            for day in range(1, last_day + 1):
                                query = {
                                    **base_query,
                                    "startDate": f"{day:02d}/{month:02d}/{year:04d}",
                                    "endDate": f"{day:02d}/{month:02d}/{year:04d}",
                                }
                                shards.append(
                                    (
                                        f"earthquakes-{year:04d}-{month:02d}-{day:02d}.csv",
                                        query,
                                    )
                                )
                            continue
                        query = {
                            **base_query,
                            "startDate": f"01/{month:02d}/{year:04d}",
                            "endDate": f"{last_day:02d}/{month:02d}/{year:04d}",
                        }
                        shards.append(
                            (f"earthquakes-{year:04d}-{month:02d}.csv", query)
                        )
                    continue
                query = {
                    **base_query,
                    "startDate": f"01/01/{year:04d}",
                    "endDate": f"31/12/{year:04d}",
                }
                shards.append((f"earthquakes-{year:04d}-{year:04d}.csv", query))
            first_year = last_year + 1
            continue
        shard_start = (
            start if first_year == start.year else datetime(first_year, 1, 1, tzinfo=UTC)
        )
        shard_end = (
            end if last_year == end.year else datetime(last_year, 12, 31, tzinfo=UTC)
        )
        query = {
            **base_query,
            "startDate": shard_start.strftime("%d/%m/%Y"),
            "endDate": shard_end.strftime("%d/%m/%Y"),
        }
        shards.append((f"earthquakes-{first_year:04d}-{last_year:04d}.csv", query))
        first_year = last_year + 1
    return shards


def download(config: Config) -> dict[str, str | int]:
    client = IgnClient(
        config.download_url,
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
        delay=config.request_delay_seconds,
        user_agent=config.user_agent,
    )
    completed = []
    response_bytes = 0
    skipped_existing = 0
    for filename, query in shard_queries(config):
        raw_path = config.raw_dir / filename
        if raw_path.exists():
            content_bytes = raw_path.stat().st_size
            skipped_existing += 1
        else:
            content = client.download_csv(query)
            atomic_bytes(raw_path, content)
            content_bytes = len(content)
        response_bytes += content_bytes
        completed.append(
            {
                "file": filename,
                "bytes": content_bytes,
                "start_date": query["startDate"],
                "end_date": query["endDate"],
            }
        )
    atomic_json(
        config.raw_dir / "provenance.json",
        {
            "retrieved_at_utc": datetime.now(UTC).isoformat(),
            "source": "Instituto Geografico Nacional earthquake catalogue",
            "source_url": "https://www.ign.es/web/sis-catalogo-terremotos",
            "doi": "https://doi.org/10.7419/162.03.2022",
            "query": query_from_config(config),
            "shard_years": config.shard_years,
            "coalesce_before_year": config.coalesce_before_year,
            "annual_shard_ranges": config.annual_shard_ranges,
            "monthly_shard_years": config.monthly_shard_years,
            "daily_shard_months": config.daily_shard_months,
            "raw_files": completed,
            "response_bytes": response_bytes,
        },
    )
    return {
        "raw_dir": str(config.raw_dir),
        "files": len(completed),
        "skipped_existing": skipped_existing,
        "response_bytes": response_bytes,
    }
