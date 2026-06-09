"""HTTP client for WSJ. Full Cookie header + browser-like headers."""
from __future__ import annotations
import os
import random
import time
from pathlib import Path
from typing import Any, Optional

import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) "
    "Gecko/20100101 Firefox/151.0"
)


class WSJError(Exception):
    """Base class. Subclasses map to CLI exit codes."""
    exit_code = 1
    code = "ERROR"


class SessionExpiredError(WSJError):
    exit_code = 2
    code = "SESSION_EXPIRED"


class NotFoundError(WSJError):
    exit_code = 3
    code = "NOT_FOUND"


class UpstreamError(WSJError):
    exit_code = 4
    code = "NETWORK"


def _load_dotenv() -> None:
    """Load .env from the skill directory or the current working directory only."""
    skill_dir = Path(__file__).resolve().parent.parent.parent
    for candidate in (skill_dir / ".env", Path.cwd() / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        return


class WSJClient:
    """Single-threaded, polite HTTP client for WSJ."""

    BASE = "https://www.wsj.com"
    AUDIO_RESOLVE = "https://video-api.shdsvc.dowjones.io/api/legacy/find-all-videos"

    def __init__(self, *, env_loaded: bool = False):
        if not env_loaded:
            _load_dotenv()
        self.cookie_header = self._build_cookie_header()
        self.session = requests.Session()
        self.user_agent = os.environ.get("WSJ_USER_AGENT") or DEFAULT_UA
        # WSJ is more sensitive than NYT/FT — slightly slower default.
        try:
            self.spacing_ms = int(os.environ.get("WSJ_REQUEST_SPACING_MS", "400"))
        except ValueError:
            self.spacing_ms = 400
        self.spacing_ms = max(100, min(self.spacing_ms, 5000))
        try:
            self.max_fetches = int(os.environ.get("WSJ_MAX_FETCHES", "200"))
        except ValueError:
            self.max_fetches = 200
        self._fetch_count = 0
        self._last_origin_fetch_at: float = 0.0

    def _build_cookie_header(self) -> str:
        blob = os.environ.get("WSJ_COOKIE")
        if not blob:
            raise SessionExpiredError(
                "No WSJ_COOKIE in env. Copy the full Cookie header value from a "
                "logged-in browser DevTools Network request to www.wsj.com and "
                "set it as WSJ_COOKIE in .env. See scripts/set_cookie.py."
            )
        return blob.strip()

    # WSJ rejects requests that don't carry browser-like Sec-Fetch-* headers
    # plus Referer/Origin. The HAR confirms this — strip these and the article
    # endpoint 401s.
    def _html_headers(self, *, referer: Optional[str] = None) -> dict:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": referer or f"{self.BASE}/",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
            "Cookie": self.cookie_header,
        }

    def _json_headers(self, *, referer: Optional[str] = None) -> dict:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": referer or f"{self.BASE}/",
            "Origin": self.BASE,
            "Cookie": self.cookie_header,
        }

    def _space(self) -> None:
        elapsed_ms = (time.time() - self._last_origin_fetch_at) * 1000
        jitter = random.uniform(-100, 100)
        wait_ms = self.spacing_ms + jitter - elapsed_ms
        if wait_ms > 0:
            time.sleep(wait_ms / 1000)

    def _check_budget(self) -> None:
        if self._fetch_count >= self.max_fetches:
            raise UpstreamError(
                f"Per-invocation fetch budget exhausted ({self.max_fetches}). "
                "Raise WSJ_MAX_FETCHES if intentional."
            )

    def _raise_for_status(self, r: requests.Response, url: str) -> None:
        if r.status_code in (401, 403):
            raise SessionExpiredError(
                f"WSJ returned {r.status_code} for {url}. Cookies likely expired — re-paste WSJ_COOKIE."
            )
        if r.status_code == 404:
            raise NotFoundError(f"WSJ returned 404 for {url}")
        if r.status_code >= 500 or r.status_code == 429:
            raise UpstreamError(f"WSJ returned {r.status_code} for {url}: {r.text[:200]}")
        if r.status_code >= 400:
            raise UpstreamError(f"WSJ returned {r.status_code} for {url}: {r.text[:200]}")

    def get_html(self, url: str, *, space: bool = True, referer: Optional[str] = None) -> str:
        self._check_budget()
        if space:
            self._space()
        try:
            r = self.session.get(url, headers=self._html_headers(referer=referer), timeout=30)
        except requests.RequestException as e:
            raise UpstreamError(f"network error for {url}: {e}") from e
        self._fetch_count += 1
        self._last_origin_fetch_at = time.time()
        self._raise_for_status(r, url)
        return r.text

    def get_json(self, url: str, *, space: bool = True, referer: Optional[str] = None) -> Any:
        self._check_budget()
        if space:
            self._space()
        backoff = 1.0
        for attempt in range(4):
            try:
                r = self.session.get(url, headers=self._json_headers(referer=referer), timeout=30)
            except requests.RequestException as e:
                raise UpstreamError(f"network error for {url}: {e}") from e
            self._fetch_count += 1
            self._last_origin_fetch_at = time.time()
            if r.status_code in (429, 503):
                retry_after = r.headers.get("Retry-After")
                wait = float(retry_after) if (retry_after and retry_after.isdigit()) else backoff
                wait = min(wait, 30.0)
                if attempt >= 3:
                    raise UpstreamError(
                        f"WSJ returned {r.status_code} repeatedly; giving up after backoff."
                    )
                time.sleep(wait)
                backoff = min(backoff * 2, 30.0)
                continue
            self._raise_for_status(r, url)
            try:
                return r.json()
            except ValueError as e:
                raise UpstreamError(f"non-JSON response from {url}: {e}") from e
        raise UpstreamError(f"exhausted retries for {url}")

    def get_bytes(self, url: str, *, space: bool = True) -> bytes:
        self._check_budget()
        if space:
            self._space()
        try:
            r = self.session.get(url, headers={"User-Agent": self.user_agent}, timeout=60)
        except requests.RequestException as e:
            raise UpstreamError(f"network error for {url}: {e}") from e
        self._fetch_count += 1
        self._last_origin_fetch_at = time.time()
        self._raise_for_status(r, url)
        return r.content
