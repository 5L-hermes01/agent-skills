"""Shared base for FT / NYT / WSJ reader skills."""
from .cache import Cache
from .cli import add_common_flags, emit, wrap
from .client import BaseClient, CookieAuthMixin, DEFAULT_UA
from .dotenv import load_dotenv
from .errors import (
    NotFoundError,
    ReaderError,
    SessionExpiredError,
    UpstreamError,
)

__all__ = [
    "BaseClient",
    "CookieAuthMixin",
    "Cache",
    "DEFAULT_UA",
    "NotFoundError",
    "ReaderError",
    "SessionExpiredError",
    "UpstreamError",
    "add_common_flags",
    "emit",
    "load_dotenv",
    "wrap",
]
