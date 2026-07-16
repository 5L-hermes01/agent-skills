"""WSJ HTTP client.

Two transport paths:

* HTML / JSON transport (cookies + browser-like headers) — used for article-body
  extraction and the legacy audio resolver. Subject to Datadome bot protection;
  cookies last ~24h in practice.
* GraphQL transport (NO auth, no cookies) — used for headlines + audio
  resolution. Hits shared-data.dowjones.io which is not Datadome-protected and
  works indefinitely without re-paste.

The cookie is loaded lazily; only the cookie-bound transports touch it.
"""
from __future__ import annotations
import json as _json
import os
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import requests

from news_reader_base import BaseClient, load_dotenv
from news_reader_base.errors import (
    NotFoundError as _NotFound,
    SessionExpiredError as _SessionExpired,
    UpstreamError as _Upstream,
)


class WSJError(Exception):
    exit_code = 1
    code = "ERROR"


class SessionExpiredError(WSJError, _SessionExpired):
    exit_code = 2
    code = "SESSION_EXPIRED"


class NotFoundError(WSJError, _NotFound):
    exit_code = 3
    code = "NOT_FOUND"


class UpstreamError(WSJError, _Upstream):
    exit_code = 4
    code = "NETWORK"


class WSJClient(BaseClient):
    """Single-threaded, polite HTTP client for WSJ."""

    SOURCE = "WSJ"

    BASE = "https://www.wsj.com"
    AUDIO_RESOLVE = "https://video-api.shdsvc.dowjones.io/api/legacy/find-all-videos"
    GRAPHQL_BASE = "https://shared-data.dowjones.io/gateway/graphql"
    # Apollo client identifier — same value the WSJ web bundle sends. The
    # GraphQL gateway requires it but does not validate it against an account.
    GRAPHQL_CLIENT_NAME = "wsj-generator-olympia"
    GRAPHQL_CLIENT_VERSION = "article"

    def __init__(self, *, env_loaded: bool = False):
        if not env_loaded:
            load_dotenv(Path(__file__).resolve().parent.parent.parent)
        super().__init__(
            session_expired_cls=SessionExpiredError,
            not_found_cls=NotFoundError,
            upstream_cls=UpstreamError,
        )
        # Cookie loaded lazily — only the HTML/JSON transports touch it.
        self._cookie_header: Optional[str] = None
        # WSJ defaults to a slightly slower cadence (400ms) than other sources.
        try:
            self.spacing_ms = int(os.environ.get("WSJ_REQUEST_SPACING_MS", "400"))
        except ValueError:
            self.spacing_ms = 400
        self.spacing_ms = max(100, min(self.spacing_ms, 5000))

    @property
    def cookie_header(self) -> str:
        """Resolve and cache the cookie blob. Raises SessionExpiredError if absent."""
        if self._cookie_header is not None:
            return self._cookie_header
        blob = os.environ.get("WSJ_COOKIE")
        if not blob:
            raise SessionExpiredError(
                "No WSJ_COOKIE in env. Copy the full Cookie header value from a "
                "logged-in browser DevTools Network request to www.wsj.com and "
                "set it as WSJ_COOKIE in .env. See scripts/set_cookie.py. "
                "(Tip: 'wsj headlines' works WITHOUT cookies via --via=graphql.)"
            )
        self._cookie_header = blob.strip()
        return self._cookie_header

    def _html_headers(self, *, referer: Optional[str] = None) -> dict:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
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
            "Accept-Encoding": "gzip, deflate",
            "Referer": referer or f"{self.BASE}/",
            "Origin": self.BASE,
            "Cookie": self.cookie_header,
        }

    def _graphql_headers(self) -> dict:
        """No Authorization. Cookie is now required — WSJ started enforcing it."""
        return {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Referer": f"{self.BASE}/",
            "Origin": self.BASE,
            "Cookie": self.cookie_header,
            "apollographql-client-name": self.GRAPHQL_CLIENT_NAME,
            "apollographql-client-version": self.GRAPHQL_CLIENT_VERSION,
        }

    # Default for arbitrary get_json/get_bytes calls.
    def _headers(self) -> dict:
        return self._json_headers()

    def get_json(
        self,
        url: str,
        *,
        headers: Optional[dict] = None,
        space: bool = True,
        referer: Optional[str] = None,
    ) -> Any:
        """Override to accept a referer kwarg for the cookie-bound JSON transport."""
        if headers is None and referer is not None:
            headers = self._json_headers(referer=referer)
        return super().get_json(url, headers=headers, space=space)

    # ----- transports --------------------------------------------------

    def graphql_get(
        self,
        sha256_hash: str,
        variables: Optional[dict] = None,
        *,
        space: bool = True,
    ) -> Any:
        """Hit the WSJ GraphQL gateway with a persisted query. No auth required."""
        params = {
            "variables": _json.dumps(variables or {}, separators=(",", ":")),
            "extensions": _json.dumps(
                {"persistedQuery": {"version": 1, "sha256Hash": sha256_hash}},
                separators=(",", ":"),
            ),
        }
        url = f"{self.GRAPHQL_BASE}?{urlencode(params)}"
        payload = self.get_json(url, headers=self._graphql_headers(), space=space)
        # Even HTTP 200 can carry a GraphQL error payload.
        if isinstance(payload, dict) and payload.get("errors") and not payload.get("data"):
            err = payload["errors"][0] if payload["errors"] else {}
            raise UpstreamError(
                f"WSJ GraphQL error: {err.get('message', 'unknown error')}"
            )
        return payload

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

