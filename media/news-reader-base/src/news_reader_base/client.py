"""Shared HTTP client.

Single-threaded, polite client: per-request spacing with jitter, per-invocation
fetch budget, adaptive backoff on 429/503 (respects Retry-After), and unified
status-code → exception mapping.

Subclasses provide their own auth/header strategy by overriding `_headers()`
(and optionally adding `_build_cookie_header()` / `_build_session()` for cookie
or token loading). Concrete error classes are passed in via the constructor so
each skill keeps source-specific exception names (FTError, NYTError, …) while
sharing structure.
"""
from __future__ import annotations
import os
import random
import time
from typing import Any, Optional, Type

import requests

from .errors import NotFoundError, SessionExpiredError, UpstreamError

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) "
    "Gecko/20100101 Firefox/151.0"
)


class BaseClient:
    """Common HTTP plumbing for reader skills.

    Subclasses set:
      - `SOURCE` class attr (e.g. "FT", "NYT", "WSJ") — used in error messages
        and env-var prefixes (SOURCE_REQUEST_SPACING_MS, SOURCE_MAX_FETCHES,
        SOURCE_USER_AGENT).
      - Concrete error classes via the constructor: pass the source-specific
        subclasses of SessionExpiredError, NotFoundError, UpstreamError.
      - Override `_headers()` to add Referer/Origin/Cookie/etc per request.
    """

    SOURCE: str = "READER"

    def __init__(
        self,
        *,
        session_expired_cls: Type[SessionExpiredError] = SessionExpiredError,
        not_found_cls: Type[NotFoundError] = NotFoundError,
        upstream_cls: Type[UpstreamError] = UpstreamError,
    ):
        self._SessionExpired = session_expired_cls
        self._NotFound = not_found_cls
        self._Upstream = upstream_cls
        self.session = requests.Session()
        self.user_agent = (
            os.environ.get(f"{self.SOURCE}_USER_AGENT") or DEFAULT_UA
        )
        try:
            self.spacing_ms = int(
                os.environ.get(f"{self.SOURCE}_REQUEST_SPACING_MS", "350")
            )
        except ValueError:
            self.spacing_ms = 350
        self.spacing_ms = max(100, min(self.spacing_ms, 5000))
        try:
            self.max_fetches = int(
                os.environ.get(f"{self.SOURCE}_MAX_FETCHES", "200")
            )
        except ValueError:
            self.max_fetches = 200
        self._fetch_count = 0
        self._last_origin_fetch_at: float = 0.0



    # -- internal --------------------------------------------------------

    def _space(self) -> None:
        elapsed_ms = (time.time() - self._last_origin_fetch_at) * 1000
        jitter = random.uniform(-100, 100)
        wait_ms = self.spacing_ms + jitter - elapsed_ms
        if wait_ms > 0:
            time.sleep(wait_ms / 1000)

    def _check_budget(self) -> None:
        if self._fetch_count >= self.max_fetches:
            raise self._Upstream(
                f"Per-invocation fetch budget exhausted ({self.max_fetches}). "
                f"Raise {self.SOURCE}_MAX_FETCHES if intentional."
            )

    def _raise_for_status(self, r: requests.Response, url: str) -> None:
        if r.status_code in (401, 403):
            raise self._SessionExpired(
                f"{self.SOURCE} returned {r.status_code} for {url}. "
                "Cookies likely expired — re-paste from browser."
            )
        if r.status_code == 404:
            raise self._NotFound(f"{self.SOURCE} returned 404 for {url}")
        if r.status_code >= 400:
            raise self._Upstream(
                f"{self.SOURCE} returned {r.status_code} for {url}: {r.text[:200]}"
            )

    # -- public ---------------------------------------------------------

    def _request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        space: bool = True,
        timeout: int = 30,
        binary: bool = False,
    ) -> requests.Response:
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL scheme: {url}")
        self._check_budget()
        if space:
            self._space()

        h = headers if headers is not None else self._headers()
        backoff = 1.0

        for attempt in range(4):
            try:
                r = self.session.request(method, url, headers=h, timeout=timeout)  # nosec B310
            except requests.RequestException as e:
                raise self._Upstream(f"network error for {url}: {e}") from e

            self._fetch_count += 1
            self._last_origin_fetch_at = time.time()

            if r.status_code in (429, 503):
                retry_after = r.headers.get("Retry-After")
                wait = (
                    float(retry_after)
                    if (retry_after and retry_after.isdigit())
                    else backoff
                )
                wait = min(wait, 30.0)
                if attempt >= 3:
                    raise self._Upstream(
                        f"{self.SOURCE} returned {r.status_code} repeatedly; "
                        "giving up after backoff."
                    )
                time.sleep(wait)
                backoff = min(backoff * 2, 30.0)
                continue

            self._raise_for_status(r, url)
            return r

        raise self._Upstream(f"exhausted retries for {url}")

    def get_json(
        self,
        url: str,
        *,
        headers: Optional[dict] = None,
        space: bool = True,
    ) -> Any:
        r = self._request(url, headers=headers, space=space)
        try:
            return r.json()
        except ValueError as e:
            raise self._Upstream(f"non-JSON response from {url}: {e}") from e

    def get_bytes(
        self,
        url: str,
        *,
        headers: Optional[dict] = None,
        space: bool = True,
    ) -> bytes:
        r = self._request(url, headers=headers, space=space, timeout=60)
        return r.content


class CookieAuthMixin:
    """Mixin to handle cookie-based authentication for readers."""

    REQUIRED_COOKIES: list[str] = []

    def _build_cookie_header(self) -> str:
        cookies = {}
        for name in self.REQUIRED_COOKIES:
            val = os.environ.get(f"{self.SOURCE}_{name}")
            if not val:
                raise self._SessionExpired(
                    f"Missing required cookie {name} for {self.SOURCE}. "
                    f"Set {self.SOURCE}_{name} in environment."
                )
            cookies[name] = val
        return "; ".join([f"{k}={v}" for k, v in cookies.items()])

    @property
    def cookie_header(self) -> str:
        """Public property to trigger cookie validation lazily."""
        return self._build_cookie_header()

    def _headers(self) -> dict:
        h = {"User-Agent": self.user_agent, "Accept": "application/json"}
        cookie_str = self._build_cookie_header()
        if cookie_str:
            h["Cookie"] = cookie_str
        return h
