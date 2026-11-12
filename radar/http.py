"""Minimal HTTP client: retries, a real user agent, and an on-disk cache.

Standard library only. A cached response is what makes a run reproducible and
what lets the test suite run without a network.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from typing import Dict, Optional

USER_AGENT = (
    "funding-radar/1.0 (+https://github.com/sadok-ayari/funding-radar) "
    "python-urllib"
)


class FetchError(RuntimeError):
    pass


def _cache_file(cache_dir: Optional[str], url: str, method: str, body: Optional[bytes]) -> Optional[str]:
    if not cache_dir:
        return None
    digest = hashlib.sha256((method + url + (body or b"").decode("utf-8", "replace")).encode()).hexdigest()[:16]
    return os.path.join(cache_dir, digest + ".json")


def request(
    url: str,
    *,
    method: str = "GET",
    body: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    retries: int = 2,
    cache_dir: Optional[str] = None,
    offline: bool = False,
    backoff: float = 1.5,
) -> str:
    """Return the response body as text. Cached when a cache directory is given."""
    cache_path = _cache_file(cache_dir, url, method, body)

    if offline:
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as handle:
                return json.load(handle)["body"]
        raise FetchError(f"offline and no cached response for {url}")

    if cache_path and os.path.exists(cache_path) and os.environ.get("FUNDING_RADAR_USE_CACHE") == "1":
        with open(cache_path, "r", encoding="utf-8") as handle:
            return json.load(handle)["body"]

    all_headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", "Accept": "*/*"}
    all_headers.update(headers or {})

    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            request_obj = urllib.request.Request(url, data=body, headers=all_headers, method=method)
            with urllib.request.urlopen(request_obj, timeout=timeout) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            text = raw.decode("utf-8", "replace")
            if cache_path:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as handle:
                    json.dump({"url": url, "method": method, "body": text}, handle)
            return text
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise FetchError(f"{method} {url} failed after {retries + 1} attempts: {last_error}")
