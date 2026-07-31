"""WSJ HTTP client.

Three transport paths:

* HTML / JSON transport (cookies + browser-like headers) — used for article-body
  extraction and the legacy audio resolver. Subject to Datadome bot protection;
  cookies last ~24h in practice.
* Public HTML transport (no cookies) — used for homepage headline discovery.
* GraphQL transport — optional collection/audio metadata transport. WSJ has
  required cookies since mid-2026, so it is no longer the default headline
  source.

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

from news_reader_base import BaseClient, CookieAuthMixin, load_dotenv
from news_reader_base.errors import create_reader_errors

# Create WSJ-specific error classes dynamically
ERRORS = create_reader_errors("WSJ")
WSJError = ERRORS["WSJError"]
SessionExpiredError = ERRORS["WSJSessionExpiredError"]
NotFoundError = ERRORS["WSJNotFoundError"]
UpstreamError = ERRORS["WSJUpstreamError"]

class WSJClient(BaseClient, CookieAuthMixin):
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
        # WSJ defaults to a slightly slower cadence (400ms) than other sources.
        try:
            self.spacing_ms = int(os.environ.get("WSJ_REQUEST_SPACING_MS", "400"))
        except ValueError:
            self.spacing_ms = 400
        self.spacing_ms = max(100, min(self.spacing_ms, 5000))

    def _build_cookie_header(self) -> str:
        """Resolve and cache the cookie blob. Raises SessionExpiredError if absent."""
        blob = os.environ.get("WSJ_COOKIE")
        if not blob:
            raise SessionExpiredError(
                "No WSJ_COOKIE in env. Copy the full Cookie header value from a "
                "logged-in browser DevTools Network request to www.wsj.com and "
                "set it as WSJ_COOKIE in .env. See scripts/set_cookie.py. "
                "(Tip: 'wsj headlines' works WITHOUT cookies via the homepage "
                "transport.)"
            )
        return blob.strip().encode("ascii", errors="replace").decode("ascii")

    def _public_html_headers(self, *, referer: Optional[str] = None) -> dict:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Priority": "u=0, i",
            "DNT": "1",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    def _html_headers(self, *, referer: Optional[str] = None) -> dict:
        h = super()._headers()
        h.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Referer": referer or f"{self.BASE}/",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
        })
        return h

    def _json_headers(self, *, referer: Optional[str] = None) -> dict:
        h = super()._headers()
        h.update({
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Referer": referer or f"{self.BASE}/",
            "Origin": self.BASE,
        })
        return h

    def _graphql_headers(self) -> dict:
        """No Authorization. Cookie is now required."""
        h = {"User-Agent": self.user_agent}
        h.update({
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Referer": f"{self.BASE}/",
            "Origin": self.BASE,
            "Cookie": self.cookie_header,
            "apollographql-client-name": self.GRAPHQL_CLIENT_NAME,
            "apollographql-client-version": self.GRAPHQL_CLIENT_VERSION,
        })
        return h

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
        if headers is None and referer is not None:
            headers = self._json_headers(referer=referer)
        return super().get_json(url, headers=headers, space=space)

    def graphql_get(
        self,
        sha256_hash: str,
        variables: Optional[dict] = None,
        *,
        space: bool = True,
    ) -> Any:
        """Hit the WSJ GraphQL gateway with a persisted query."""
        params = {
            "variables": _json.dumps(variables or {}, separators=(",", ":")),
            "extensions": _json.dumps(
                {"persistedQuery": {"version": 1, "sha256Hash": sha256_hash}},
                separators=(",", ":"),
            ),
        }
        url = f"{self.GRAPHQL_BASE}?{urlencode(params)}"
        payload = self.get_json(url, headers=self._graphql_headers(), space=space)
        if isinstance(payload, dict) and payload.get("errors") and not payload.get("data"):
            err = payload["errors"][0] if payload["errors"] else {}
            raise UpstreamError(
                f"WSJ GraphQL error: {err.get('message', 'unknown error')}"
            )
        return payload

    def get_html(self, url: str, *, space: bool = True, referer: Optional[str] = None) -> str:
        r = self._request(url, headers=self._html_headers(referer=referer), space=space, timeout=30)
        return r.text

    def get_public_html(
        self,
        url: str,
        *,
        space: bool = True,
        referer: Optional[str] = None,
    ) -> str:
        """Fetch public HTML without reading or sending WSJ_COOKIE."""
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL scheme: {url}")
        self._check_budget()
        if space:
            self._space()
        try:
            r = self.session.get(
                url,
                headers=self._public_html_headers(referer=referer),
                timeout=30,
            )  # nosec B310
        except requests.RequestException as e:
            raise UpstreamError(f"network error for {url}: {e}") from e
        self._fetch_count += 1
        self._last_origin_fetch_at = time.time()
        if r.status_code == 404:
            raise NotFoundError(f"{self.SOURCE} returned 404 for {url}")
        if r.status_code >= 400:
            raise UpstreamError(
                f"{self.SOURCE} public homepage fetch returned {r.status_code} "
                f"for {url}: {r.text[:200]}"
            )
        return r.text
