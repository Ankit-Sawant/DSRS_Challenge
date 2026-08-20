from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

SEC_ROOT = "https://www.sec.gov"
DATA_ROOT = "https://data.sec.gov"


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    requests: int = 0


class SECClient:
    """Small SEC client with disk caching, backoff, and conservative rate limiting."""

    def __init__(
        self,
        user_agent: str,
        cache_dir: Path,
        *,
        requests_per_second: float = 5.0,
        timeout: float = 30.0,
        max_attempts: int = 5,
    ) -> None:
        self.user_agent = user_agent.strip()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = 1.0 / requests_per_second
        self.timeout = timeout
        self.max_attempts = max_attempts
        self._last_request_at = 0.0
        self.stats = CacheStats()
        self._client = httpx.Client(
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json,text/plain,application/xml,text/xml,*/*",
            },
            timeout=self.timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SECClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _wait_for_slot(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def _request(self, url: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            self._wait_for_slot()
            try:
                response = self._client.get(url)
                self._last_request_at = time.monotonic()
                self.stats.requests += 1

                if response.status_code == 200:
                    return response.content

                if response.status_code in {403, 429, 500, 502, 503, 504}:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        delay = max(1.0, float(retry_after))
                    else:
                        delay = min(30.0, 2.0 ** attempt)
                    time.sleep(delay)
                    continue

                response.raise_for_status()
            except Exception as exc:  # network errors also get bounded backoff
                last_error = exc
                time.sleep(min(30.0, 2.0 ** attempt))

        if last_error is not None:
            raise RuntimeError(f"SEC request failed after retries: {url}: {last_error}") from last_error
        raise RuntimeError(f"SEC request failed after retries: {url}")

    def get_bytes(self, url: str, cache_key: str) -> bytes:
        path = self.cache_dir / cache_key
        if path.exists():
            self.stats.hits += 1
            return path.read_bytes()

        self.stats.misses += 1
        data = self._request(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return data

    def get_json(self, url: str, cache_key: str) -> dict[str, Any]:
        return json.loads(self.get_bytes(url, cache_key).decode("utf-8"))

    def get_text(self, url: str, cache_key: str, encoding: str = "utf-8") -> str:
        return self.get_bytes(url, cache_key).decode(encoding, errors="replace")
