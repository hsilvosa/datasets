from __future__ import annotations

import http.client
import random
import time
import urllib.error
import urllib.request
import uuid

PREFIX = "_IGNSISCatalogoTerremotos_WAR_IGNSISCatalogoTerremotosportlet_"


def encode_multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----ign-earthquakes-{uuid.uuid4().hex}"
    blocks: list[bytes] = []
    for name, value in fields.items():
        blocks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    blocks.append(f"--{boundary}--\r\n".encode())
    return b"".join(blocks), boundary


class IgnClient:
    def __init__(
        self,
        download_url: str,
        *,
        timeout: int = 60,
        max_retries: int = 3,
        delay: float = 0.2,
        user_agent: str = "public-data-research-ign-earthquakes/0.1",
    ) -> None:
        self.download_url = download_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.delay = delay
        self.user_agent = user_agent

    def download_csv(self, query: dict[str, str]) -> bytes:
        fields = {f"{PREFIX}{key}": value for key, value in query.items()}
        fields[f"{PREFIX}tipoDescarga"] = "csv"
        body, boundary = encode_multipart(fields)
        headers = {
            "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.1",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": self.user_agent,
        }
        for attempt in range(self.max_retries + 1):
            if self.delay:
                time.sleep(self.delay)
            request = urllib.request.Request(
                self.download_url, data=body, headers=headers, method="POST"
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    content = response.read()
                    return content
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                OSError,
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
                    raise RuntimeError("IGN catalogue download failed") from exc
                time.sleep(min(30.0, 2**attempt + random.random()))
        raise AssertionError("Retry loop exited unexpectedly")
