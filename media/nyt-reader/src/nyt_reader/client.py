"""HTTP client for NYT. Cookie session + the 3 static project-vi headers."""
from __future__ import annotations
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) "
    "Gecko/20100101 Firefox/151.0"
)

# Static client identifier extracted from the NYT web bundle (samizdat-graphql
# "project-vi" client). NYT validates this token on every GraphQL request but
# the value itself is public and constant across all browser sessions. Override
# via NYT_TOKEN env if NYT rotates it.
DEFAULT_NYT_TOKEN = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAs+/oUCTBmD/cLdmcecrnBMHiU/p"
    "xQCn2DDyaPKUOXxi4p0uUSZQzsuq1pJ1m5z1i0YGPd1U1OeGHAChWtqoxC7bFMCXcwnE1oy"
    "ui9G1uobgpm1GdhtwkR7ta7akVTcsF8zxiXx7DNXIPd2nIJFH83rmkZueKrC4JVaNzjvD+Z"
    "03piLn5bHWU6+w+rA+kyJtGgZNTXKyPh6EC6o5N+rknNMG5+CdTq35p8f99WjFawSvYgP9V"
    "64kgckbTbtdJ6YhVP58TnuYgr12urtwnIqWP9KSJ1e5vmgf3tunMqWNm6+AnsqNj8mCLdCu"
    "c5cEB74CwUeQcP2HQQmbCddBy2y0mEwIDAQAB"
)


class NYTError(Exception):
    """Base class. Subclasses map to CLI exit codes."""
    exit_code = 1
    code = "ERROR"


class SessionExpiredError(NYTError):
    exit_code = 2
    code = "SESSION_EXPIRED"


class NotFoundError(NYTError):
    exit_code = 3
    code = "NOT_FOUND"


class UpstreamError(NYTError):
    exit_code = 4
    code = "NETWORK"


def _load_dotenv() -> None:
    """Load .env from the skill directory or the current working directory only.

    Deliberately does NOT walk up the filesystem.
    """
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


class NYTClient:
    """Single-threaded, polite HTTP client for NYT."""

    GRAPHQL = "https://samizdat-graphql.nytimes.com/graphql/v2"
    BASE = "https://www.nytimes.com"

    NAMED_COOKIES = (
        ("NYT_A", "nyt-a"),
        ("NYT_S", "NYT-S"),
        ("NYT_JKIDD", "nyt-jkidd"),
        ("NYT_PURR", "nyt-purr"),
        ("NYT_B_SID", "nyt-b-sid"),
    )

    def __init__(self, *, env_loaded: bool = False):
        if not env_loaded:
            _load_dotenv()
        self.cookie_header = self._build_cookie_header()
        self.session = requests.Session()
        self.user_agent = os.environ.get("NYT_USER_AGENT") or DEFAULT_UA
        self.nyt_token = os.environ.get("NYT_TOKEN") or DEFAULT_NYT_TOKEN
        try:
            self.spacing_ms = int(os.environ.get("NYT_REQUEST_SPACING_MS", "350"))
        except ValueError:
            self.spacing_ms = 350
        self.spacing_ms = max(100, min(self.spacing_ms, 5000))
        try:
            self.max_fetches = int(os.environ.get("NYT_MAX_FETCHES", "200"))
        except ValueError:
            self.max_fetches = 200
        self._fetch_count = 0
        self._last_origin_fetch_at: float = 0.0

    def _build_cookie_header(self) -> str:
        missing = [env_name for env_name, _ in self.NAMED_COOKIES if not os.environ.get(env_name)]
        if missing:
            raise SessionExpiredError(
                "No NYT credentials in env. Set the five named cookies: "
                f"{', '.join(n for n, _ in self.NAMED_COOKIES)}. Missing: {', '.join(missing)}."
            )
        return "; ".join(
            f"{cookie}={os.environ[env_name]}"
            for env_name, cookie in self.NAMED_COOKIES
        )

    def _graphql_headers(self) -> dict:
        return {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.BASE}/",
            "Origin": self.BASE,
            "content-type": "application/json",
            "nyt-app-type": "project-vi",
            "nyt-app-version": "0.0.5",
            "nyt-token": self.nyt_token,
            "Cookie": self.cookie_header,
        }

    def _html_headers(self) -> dict:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.BASE}/",
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
                "Raise NYT_MAX_FETCHES if intentional."
            )

    def _raise_for_status(self, r: requests.Response, url: str) -> None:
        if r.status_code in (401, 403):
            raise SessionExpiredError(
                f"NYT returned {r.status_code} for {url}. Cookies/token likely expired — re-paste."
            )
        if r.status_code == 404:
            raise NotFoundError(f"NYT returned 404 for {url}")
        if r.status_code >= 500 or r.status_code == 429:
            raise UpstreamError(f"NYT returned {r.status_code} for {url}: {r.text[:200]}")
        if r.status_code >= 400:
            raise UpstreamError(f"NYT returned {r.status_code} for {url}: {r.text[:200]}")

    def graphql(
        self,
        operation_name: str,
        *,
        sha256_hash: str,
        variables: Optional[dict] = None,
        space: bool = True,
    ) -> Any:
        """Replay a NYT persisted GraphQL query by name + hash."""
        params = {
            "operationName": operation_name,
            "variables": json.dumps(variables or {}, separators=(",", ":")),
            "extensions": json.dumps({
                "persistedQuery": {"version": 1, "sha256Hash": sha256_hash}
            }, separators=(",", ":")),
        }
        url = f"{self.GRAPHQL}?{urlencode(params)}"
        return self._get_json(url, headers=self._graphql_headers(), space=space)

    def get_html(self, url: str, *, space: bool = True) -> str:
        self._check_budget()
        if space:
            self._space()
        try:
            r = self.session.get(url, headers=self._html_headers(), timeout=30)
        except requests.RequestException as e:
            raise UpstreamError(f"network error for {url}: {e}") from e
        self._fetch_count += 1
        self._last_origin_fetch_at = time.time()
        self._raise_for_status(r, url)
        return r.text

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

    def _get_json(self, url: str, *, headers: dict, space: bool) -> Any:
        self._check_budget()
        if space:
            self._space()
        backoff = 1.0
        for attempt in range(4):
            try:
                r = self.session.get(url, headers=headers, timeout=30)
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
                        f"NYT returned {r.status_code} repeatedly; giving up after backoff."
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
