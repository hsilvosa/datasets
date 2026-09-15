from __future__ import annotations

import http.client
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Response:
    status: int
    content: bytes
    headers: dict[str, str]

    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class RateLimiter:
    """Enforces a minimum interval between requests shared across all workers."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.delay
        if sleep_for > 0:
            time.sleep(sleep_for)


class BoeClient:
    def __init__(
        self,
        *,
        timeout: int = 120,
        max_retries: int = 5,
        rate_limiter: RateLimiter | None = None,
        user_agent: str = "public-data-research-boe-borme/0.1",
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limiter = rate_limiter or RateLimiter(0.0)
        self.user_agent = user_agent

    def get(
        self,
        url: str,
        *,
        accept: str = "application/json",
        if_modified_since: str | None = None,
        if_none_match: str | None = None,
    ) -> Response:
        headers = {"Accept": accept, "User-Agent": self.user_agent}
        if if_modified_since:
            headers["If-Modified-Since"] = if_modified_since
        if if_none_match:
            headers["If-None-Match"] = if_none_match
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.rate_limiter.wait()
            request = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return Response(
                        status=response.status,
                        content=response.read(),
                        headers=dict(response.headers.items()),
                    )
            except urllib.error.HTTPError as exc:
                if exc.code in (304, 404):
                    return Response(status=exc.code, content=b"", headers=dict(exc.headers.items()))
                last_error = exc
                if exc.code not in RETRYABLE_STATUS or attempt >= self.max_retries:
                    raise RuntimeError(f"Request failed with HTTP {exc.code}: {url}") from exc
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                OSError,
                http.client.HTTPException,
            ) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Request failed: {url}") from exc
            time.sleep(min(60.0, (2**attempt) + random.random()))
        raise RuntimeError(f"Request failed after retries: {url}") from last_error
