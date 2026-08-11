from __future__ import annotations

import http.client
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any


class CimaClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: int = 60,
        max_retries: int = 5,
        delay: float = 0.2,
        user_agent: str = "public-data-research-cima/0.1",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.delay = delay
        self.headers = {"Accept": "application/json", "User-Agent": user_agent}

    def get(self, endpoint: str, **params: Any) -> Any:
        query = urllib.parse.urlencode(
            [(key, value) for key, value in params.items() if value is not None], doseq=True
        )
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        for attempt in range(self.max_retries + 1):
            if self.delay:
                time.sleep(self.delay)
            try:
                request = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    content = response.read()
                    if not content:
                        return None
                    return json.loads(content.decode("utf-8"))
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                http.client.HTTPException,
            ) as exc:
                retryable = not isinstance(exc, urllib.error.HTTPError) or exc.code in {
                    408,
                    425,
                    429,
                    500,
                    502,
                    503,
                    504,
                }
                if attempt >= self.max_retries or not retryable:
                    raise RuntimeError(f"CIMA request failed: {url}") from exc
                time.sleep(min(30.0, 2**attempt + random.random()))
        raise AssertionError("Retry loop exited unexpectedly")

    def paginated(
        self, endpoint: str, *, max_pages: int | None = None, **params: Any
    ) -> Iterator[dict]:
        page = 1
        while max_pages is None or page <= max_pages:
            payload = self.get(endpoint, pagina=page, **params)
            if payload is None:
                break
            if isinstance(payload, list):
                rows = payload
                total_pages = page
            else:
                rows = payload.get("resultados", [])
                total_rows = payload.get("totalFilas")
                page_size = payload.get("tamanioPagina") or len(rows)
                total_pages = (
                    (int(total_rows) + int(page_size) - 1) // int(page_size)
                    if total_rows is not None and page_size
                    else page
                )
            if not rows:
                break
            yield from rows
            if page >= total_pages:
                break
            page += 1
