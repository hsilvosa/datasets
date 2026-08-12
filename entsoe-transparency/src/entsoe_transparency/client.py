from __future__ import annotations

import os
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


class MissingCredential(RuntimeError):
    pass


class EntsoeResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResponseInfo:
    content: bytes
    status: str
    reason_code: str | None
    reason_text: str | None


def load_token(name: str, env_file: Path) -> str:
    token = os.environ.get(name)
    if token:
        return token
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == name:
                token = value.strip().strip('"').strip("'")
                if token:
                    return token
    raise MissingCredential(f"Set {name} in the environment or in {env_file.name}")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def inspect_response(content: bytes) -> ResponseInfo:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise EntsoeResponseError("ENTSO-E returned invalid XML") from exc
    if _local_name(root.tag) != "Acknowledgement_MarketDocument":
        return ResponseInfo(content, "data", None, None)
    code = None
    text = None
    for element in root.iter():
        name = _local_name(element.tag)
        if name == "code" and code is None:
            code = element.text
        elif name == "text" and text is None:
            text = element.text
    normalized = (text or "").lower()
    if "no matching data" in normalized or "no data" in normalized:
        return ResponseInfo(content, "no_data", code, text)
    raise EntsoeResponseError(f"ENTSO-E rejected the request (reason {code or 'unknown'})")


class RateLimiter:
    def __init__(self, requests_per_second: float):
        self.interval = 1.0 / requests_per_second
        self.lock = threading.Lock()
        self.next_allowed = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_allowed - now)
            self.next_allowed = max(now, self.next_allowed) + self.interval
        if delay:
            time.sleep(delay)


class EntsoeClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int,
        max_retries: int,
        user_agent: str,
        limiter: RateLimiter,
    ):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent
        self.limiter = limiter

    def get(self, parameters: dict[str, str]) -> ResponseInfo:
        query = urllib.parse.urlencode({"securityToken": self.token, **parameters})
        url = f"{self.base_url}?{query}"
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            request = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent, "Accept": "application/xml,text/xml"},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return inspect_response(response.read())
            except EntsoeResponseError:
                raise
            except urllib.error.HTTPError as exc:
                retryable = exc.code in {429, 500, 502, 503, 504}
                if not retryable or attempt >= self.max_retries:
                    raise EntsoeResponseError(
                        f"ENTSO-E request failed with HTTP {exc.code}; credentials suppressed"
                    ) from exc
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(60.0, 2**attempt)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt >= self.max_retries:
                    raise EntsoeResponseError(
                        "ENTSO-E request failed after retries; credentials suppressed"
                    ) from exc
                delay = min(60.0, 2**attempt + random.random())
            time.sleep(delay)
        raise AssertionError("unreachable")
