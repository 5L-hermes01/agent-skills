"""HTTP client for FT.com. Cookie-based auth, jittered spacing, adaptive backoff."""
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


class FTError(Exception):
    """Base class. Subclasses map to CLI exit codes."""
    exit_code = 1
    code = "ERROR"


class SessionExpiredError(FTError):
    exit_code = 2
    code = "SESSION_EXPIRED"


class NotFoundError(FTError):
    exit_code = 3
    code = "NOT_FOUND"


class UpstreamError(FTError):
    exit_code = 4
    code = "NETWORK"


def _load_dotenv() -> None:
    """Load .env from the skill directory or the current working directory only.

    Deliberately does NOT walk up the filesystem — that would let unrelated
    project .env files (or ~/.env) leak credentials into this skill's process.
    """
    skill_dir = Path(__file__).resolve().parent.parent.parent
    candidates = [skill_dir / ".env", Path.cwd() / ".env"]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)
        return


class FTClient:
    """Single-threaded, polite HTTP client for FT.com."""

    APP_API = "https://app-api.ft.com"
    AUDIO_CHECK = "https://audio-available.ft.com"

    NAMED_COOKIES = (
        ("FT_SESSION_S", "FTSession_s"),
        ("FT_CLIENT_SESSION_ID", "FTClientSessionId"),
        ("FT_APP_USER", "AppUser"),
        ("FT_CSRF", "_csrf"),
    )

    def __init__(self, *, env_loaded: bool = False):
        if not env_loaded:
            _load_dotenv()
        self.cookie_header = self._build_cookie_header()
        self.session = requests.Session()
        self.user_agent = os.environ.get("FT_USER_AGENT") or DEFAULT_UA
        try:
            self.spacing_ms = int(os.environ.get("FT_REQUEST_SPACING_MS", "350"))
        except ValueError:
            self.spacing_ms = 350
        self.spacing_ms = max(100, min(self.spacing_ms, 5000))
        try:
            self.max_fetches = int(os.environ.get("FT_MAX_FETCHES", "200"))
        except ValueError:
            self.max_fetches = 200
        self._fetch_count = 0
        self._last_origin_fetch_at: float = 0.0

    def _build_cookie_header(self) -> str:
        """Prefer FT_COOKIE (full browser Cookie header value). Fall back to the 4
        named cookies — only works for `/structure/v14` and article endpoints, not MyFT,
        because MyFT requires additional coupled cookies that resist isolation."""
        blob = os.environ.get("FT_COOKIE")
        if blob:
            return blob.strip()
        missing = [name for name, _ in self.NAMED_COOKIES if not os.environ.get(name)]
        if missing:
            raise SessionExpiredError(
                "No FT credentials in env. Set FT_COOKIE to the full Cookie header value "
                "from a browser DevTools Network request to app-api.ft.com (recommended), "
                f"or set the four legacy vars: {', '.join(n for n, _ in self.NAMED_COOKIES)}. "
                f"Missing: {', '.join(missing)}."
            )
        return "; ".join(f"{c}={os.environ[e]}" for e, c in self.NAMED_COOKIES)

    def _headers(self) -> dict:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://app.ft.com/",
            "Origin": "https://app.ft.com",
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
                "Raise FT_MAX_FETCHES if intentional."
            )

    def _raise_for_status(self, r: requests.Response, url: str) -> None:
        if r.status_code in (401, 403):
            # 403 is the FT signal for stale/insufficient session cookies.
            raise SessionExpiredError(
                f"FT returned {r.status_code} for {url}. Cookies likely expired — re-paste from browser."
            )
        if r.status_code == 404:
            raise NotFoundError(f"FT returned 404 for {url}")
        if r.status_code >= 500 or r.status_code == 429:
            raise UpstreamError(f"FT returned {r.status_code} for {url}: {r.text[:200]}")
        if r.status_code >= 400:
            raise UpstreamError(f"FT returned {r.status_code} for {url}: {r.text[:200]}")

    def get_json(self, url: str, *, space: bool = True) -> Any:
        """GET with backoff. `space` controls the polite delay (skip for one-shot endpoints)."""
        self._check_budget()
        if space:
            self._space()
        backoff = 1.0
        for attempt in range(4):
            try:
                r = self.session.get(url, headers=self._headers(), timeout=30)
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
                        f"FT returned {r.status_code} repeatedly; giving up after backoff."
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
