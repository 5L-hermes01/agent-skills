"""NYT HTTP client. Cookie session + the 3 static project-vi headers."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import requests

from news_reader_base import BaseClient, CookieAuthMixin, load_dotenv
from news_reader_base.errors import create_reader_errors

# Create NYT-specific error classes dynamically
ERRORS = create_reader_errors("NYT")
NYTError = ERRORS["NYTError"]
SessionExpiredError = ERRORS["NYTSessionExpiredError"]
NotFoundError = ERRORS["NYTNotFoundError"]
UpstreamError = ERRORS["NYTUpstreamError"]

DEFAULT_NYT_TOKEN = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAs+/oUCTBmD/cLdmcecrnBMHiU/p"
    "xQCn2DDyaPKUOXxi4p0uUSZQzsuq1pJ1m5z1i0YGPd1U1OeGHAChWtqoxC7bFMCXcwnE1oy"
    "ui9G1uobgpm1GdhtwkR7ta7akVTcsF8zxiXx7DNXIPd2nIJFH83rmkZueKrC4JVaNzjvD+Z"
    "03piLn5bHWU6+w+rA+kyJtGgZNTXKyPh6EC6o5N+rknNMG5+CdTq35p8f99WjFawSvYgP9V"
    "64kgckbTbtdJ6YhVP58TnuYgr12urtwnIqWP9KSJ1e5vmgf3tunMqWNm6+AnsqNj8mCLdCu"
    "c5cEB74CwUeQcP2HQQmbCddBy2y0mEwIDAQAB"
)


class NYTClient(BaseClient, CookieAuthMixin):
    """Single-threaded, polite HTTP client for NYT."""

    SOURCE = "NYT"
    GRAPHQL = "https://samizdat-graphql.nytimes.com/graphql/v2"
    BASE = "https://www.nytimes.com"

    # Map environment variable name -> cookie name
    REQUIRED_COOKIES = ["NYT_A", "NYT_S", "NYT_JKIDD", "NYT_PURR", "NYT_B_SID"]

    def __init__(self, *, env_loaded: bool = False):
        if not env_loaded:
            load_dotenv(Path(__file__).resolve().parent.parent.parent)
        super().__init__(
            session_expired_cls=SessionExpiredError,
            not_found_cls=NotFoundError,
            upstream_cls=UpstreamError,
        )
        self._build_cookie_header()
        self.nyt_token = os.environ.get("NYT_TOKEN") or DEFAULT_NYT_TOKEN

    def _build_cookie_header(self) -> str:
        # Override to maintain custom error message and mapping
        cookies = {}
        mapping = {
            "NYT_A": "nyt-a",
            "NYT_S": "NYT-S",
            "NYT_JKIDD": "nyt-jkidd",
            "NYT_PURR": "nyt-purr",
            "NYT_B_SID": "nyt-b-sid",
        }
        missing = [name for name in mapping if not os.environ.get(name)]
        if missing:
            raise SessionExpiredError(
                "No NYT credentials in env. Set the five named cookies: "
                f"{', '.join(mapping.keys())}. Missing: {', '.join(missing)}."
            )
        return "; ".join(f"{mapping[e]}={os.environ[e]}" for e in mapping)

    def _graphql_headers(self) -> dict:
        h = super()._headers()
        h.update({
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.BASE}/",
            "Origin": self.BASE,
            "content-type": "application/json",
            "nyt-app-type": "project-vi",
            "nyt-app-version": "0.0.5",
            "nyt-token": self.nyt_token,
        })
        return h

    def _html_headers(self) -> dict:
        h = super()._headers()
        h.update({
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.BASE}/",
        })
        return h

    def _headers(self) -> dict:
        return self._graphql_headers()

    def graphql(
        self,
        operation_name: str,
        *,
        sha256_hash: str,
        variables: Optional[dict] = None,
        space: bool = True,
    ) -> Any:
        params = {
            "operationName": operation_name,
            "variables": json.dumps(variables or {}, separators=(",", ":")),
            "extensions": json.dumps(
                {"persistedQuery": {"version": 1, "sha256Hash": sha256_hash}},
                separators=(",", ":"),
            ),
        }
        url = f"{self.GRAPHQL}?{urlencode(params)}"
        return self.get_json(url, headers=self._graphql_headers(), space=space)

    def get_html(self, url: str, *, space: bool = True) -> str:
        # Use _request to avoid duplication
        r = self._request(url, headers=self._html_headers(), space=space)
        return r.text
