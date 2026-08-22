from __future__ import annotations

import logging
import time
from datetime import date
from typing import Optional

import requests

logger = logging.getLogger(__name__)

OMIE_DOWNLOAD_URL = "https://www.omie.es/es/file-download"


class OMIEClient:
    def __init__(
        self,
        user_agent: str = "public-data-research-omie-electricity/0.1",
        timeout: int = 30,
        max_retries: int = 3,
        delay: float = 0.05,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.timeout = timeout
        self.max_retries = max_retries
        self.delay = delay

    def _fetch_file(self, parent: str, filename: str) -> Optional[bytes]:
        params = {
            "parents[0]": parent,
            "filename": filename,
        }
        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(self.delay)
                response = self.session.get(
                    OMIE_DOWNLOAD_URL,
                    params=params,
                    timeout=self.timeout,
                )
                if response.status_code == 200 and len(response.content) > 0:
                    return response.content
                if response.status_code == 404:
                    return None
            except requests.RequestException as exc:
                logger.warning(
                    "Network error fetching %s (attempt %d/%d): %s",
                    filename,
                    attempt,
                    self.max_retries,
                    exc,
                )
            time.sleep(self.delay * (2**attempt))
        return None

    def fetch_marginalpdbc(self, target_date: date) -> Optional[bytes]:
        """Fetch daily marginal price file (marginalpdbc_YYYYMMDD.1) from OMIE."""
        date_str = target_date.strftime("%Y%m%d")
        return self._fetch_file("marginalpdbc", f"marginalpdbc_{date_str}.1")

    def fetch_curva_pbc(self, target_date: date) -> Optional[bytes]:
        """Fetch daily bidding curves and market bids (curva_pbc_YYYYMMDD.1) from OMIE."""
        date_str = target_date.strftime("%Y%m%d")
        return self._fetch_file("curva_pbc", f"curva_pbc_{date_str}.1")
