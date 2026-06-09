"""NYT 'For You' / saved-articles status check.

The HAR only captured `ReadingListStatusQuery` (a per-URL boolean lookup),
not a full saved-list endpoint. This skill exposes the same status query
for callers who want to verify saved-state, and returns a clear
"NotImplemented" if asked for the full list — the downstream pipeline
doesn't need this for podcast generation (headlines already covers the
high-value content).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from .cache import Cache, TTL_SAVED
from .client import NYTClient

HASH_READING_LIST_STATUS = (
    "ba8b1888936f67c77e314ebf7c461a40787c0a684d9bb790bb40dee158b9bb54"
)


def get_saved(
    urls: Optional[list[str]] = None,
    *,
    client: Optional[NYTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    """Check saved status for a list of article URLs.

    Returns one item per URL with `saved: true|false`. Without `urls`, returns
    an empty list and a note that the full reading-list endpoint isn't yet
    wired up.
    """
    out: list[dict] = []
    if not urls:
        return {
            "schema_version": 1,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "items": [],
            "note": (
                "Full reading-list enumeration is not implemented. Pass --url "
                "to check the saved status of specific articles."
            ),
        }

    client = client or NYTClient()
    cache = cache or Cache()
    cache_url = f"{client.GRAPHQL}?op=ReadingListStatusQuery&urls={'|'.join(urls)}"
    payload = None if no_cache else cache.get_json("GET", cache_url, TTL_SAVED)
    if payload is None:
        payload = client.graphql(
            "ReadingListStatusQuery",
            sha256_hash=HASH_READING_LIST_STATUS,
            variables={"url": urls},
            space=False,
        )
        cache.set_json("GET", cache_url, payload)

    user = (payload.get("data") or {}).get("user") or {}
    saved_urls = set()
    saved_list = user.get("savedAssets") or user.get("readingList") or []
    for entry in saved_list:
        if isinstance(entry, dict) and entry.get("url"):
            saved_urls.add(entry["url"])

    for url in urls:
        out.append({"url": url, "saved": url in saved_urls})

    return {
        "schema_version": 1,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "items": out,
    }
