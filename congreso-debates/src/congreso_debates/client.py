from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

OPENDATA_BASE = "https://www.congreso.es"
INTERVENCIONES_PAGE = "https://www.congreso.es/opendata/intervenciones"


class CongresoClient:
    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        timeout: int = 45,
        max_retries: int = 3,
        delay: float = 0.05,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml,application/json,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        })
        self.timeout = timeout
        self.max_retries = max_retries
        self.delay = delay

    def discover_voting_json_urls(self, legislature: int) -> list[str]:
        """Discover voting JSON URLs from the official OpenData portal for a specific legislature."""
        url = f"https://www.congreso.es/opendata/votaciones?p_p_id=votaciones&p_p_lifecycle=0&_votaciones_legislatura={legislature}"
        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    matches = re.findall(
                        r'href="([^"]*(?:votaciones|opendata)[^"]*\.json)"',
                        resp.text,
                        re.IGNORECASE,
                    )
                    urls = []
                    for m in matches:
                        if m.startswith("http"):
                            urls.append(m)
                        else:
                            urls.append(OPENDATA_BASE + m)
                    return sorted(list(set(urls)))
            except requests.RequestException as exc:
                logger.warning("Error discovering voting URLs for Leg %d (attempt %d/%d): %s", legislature, attempt, self.max_retries, exc)
            time.sleep(self.delay * (2**attempt))
        return []

    def discover_intervenciones_urls(self) -> list[str]:
        """Discover speech and parliamentary intervention dataset dump URLs."""
        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = self.session.get(INTERVENCIONES_PAGE, timeout=self.timeout)
                if resp.status_code == 200:
                    matches = re.findall(
                        r'href="([^"]*(?:intervenciones)[^"]*\.json)"',
                        resp.text,
                        re.IGNORECASE,
                    )
                    urls = []
                    for m in matches:
                        if m.startswith("http"):
                            urls.append(m)
                        else:
                            urls.append(OPENDATA_BASE + m)
                    return sorted(list(set(urls)))
            except requests.RequestException as exc:
                logger.warning("Error discovering intervenciones URLs (attempt %d/%d): %s", attempt, self.max_retries, exc)
            time.sleep(self.delay * (2**attempt))
        return []

    def fetch_json(self, url: str) -> Optional[Any]:
        """Fetch a single JSON document (can be list or dict)."""
        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.json()
            except requests.RequestException as exc:
                logger.warning("Error fetching %s (attempt %d/%d): %s", url, attempt, self.max_retries, exc)
            time.sleep(self.delay * (2**attempt))
        return None

    def download_pdf(self, url: str, dest_path: Path) -> bool:
        """Download an official Diario de Sesiones PDF file."""
        if dest_path.exists() and dest_path.stat().st_size > 1000:
            return True
        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    dest_path.write_bytes(resp.content)
                    return True
            except requests.RequestException as exc:
                logger.warning("Error downloading PDF %s: %s", url, exc)
            time.sleep(self.delay * (2**attempt))
        return False
