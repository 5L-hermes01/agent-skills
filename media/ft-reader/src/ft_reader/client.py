"""FT-specific HTTP client. Builds on news_reader_base.BaseClient."""
from __future__ import annotations
import os
from pathlib import Path

from news_reader_base import BaseClient, CookieAuthMixin, load_dotenv
from news_reader_base.errors import create_reader_errors

# Create FT-specific error classes dynamically
ERRORS = create_reader_errors("FT")
# Alias them for compatibility with other modules that might import them
FTError = ERRORS["FTError"]
SessionExpiredError = ERRORS["FTSessionExpiredError"]
NotFoundError = ERRORS["FTNotFoundError"]
UpstreamError = ERRORS["FTUpstreamError"]

class FTClient(BaseClient, CookieAuthMixin):
    """Single-threaded, polite HTTP client for FT.com."""

    SOURCE = "FT"
    APP_API = "https://app-api.ft.com"
    AUDIO_CHECK = "https://audio-available.ft.com"

    # These are the keys we look for in env: FT_FTSession_s, etc.
    # But FT expects the Actual cookies to be FTSession_s, etc.
    # So we override _build_cookie_header.
    REQUIRED_COOKIES = [] 

    def __init__(self, *, env_loaded: bool = False):
        if not env_loaded:
            load_dotenv(Path(__file__).resolve().parent.parent.parent)
        super().__init__(
            session_expired_cls=SessionExpiredError,
            not_found_cls=NotFoundError,
            upstream_cls=UpstreamError,
        )
        self._build_cookie_header()

    def _build_cookie_header(self) -> str:
        """Prefer FT_COOKIE (full browser Cookie header). Fall back to 4 named cookies."""
        blob = os.environ.get("FT_COOKIE")
        if blob:
            return blob.strip()
        
        named = {
            "FT_SESSION_S": "FTSession_s",
            "FT_CLIENT_SESSION_ID": "FTClientSessionId",
            "FT_APP_USER": "AppUser",
            "FT_CSRF": "_csrf",
        }
        missing = [name for name in named if not os.environ.get(name)]
        if missing:
            raise SessionExpiredError(
                "No FT credentials in env. Set FT_COOKIE to the full Cookie header "
                "value from a browser DevTools Network request to app-api.ft.com "
                f"(recommended), or set the four legacy vars: {', '.join(named.keys())}. "
                f"Missing: {', '.join(missing)}."
            )
        return "; ".join(f"{c}={os.environ[e]}" for e, c in named.items())

    def _headers(self) -> dict:
        h = super()._headers()
        h.update({
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://app.ft.com/",
            "Origin": "https://app.ft.com",
        })
        return h

