"""Personalized homes → flat list of articles with inlined audio + body."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterator, Optional

from .cache import Cache, TTL_HEADLINES
from .client import NYTClient

# Persisted query hashes captured from the NYT web bundle. NYT rotates these
# on bundle releases; override via NYT_*_HASH env if upstream changes.
HASH_LEGACY_PERSONALIZED_PACKAGES = (
    "ee5c94d6a5df9803b2282c89b4666b3f58d8c0ad8d6ce48c88a1d2bd63ef5816"
)
HASH_LEGACY_GENERIC_PERSONALIZED_PACKAGES = (
    "9e65be217168b7c3cfcbc45220a957059481e68e2c9bc11f559b35adcde46b81"
)

# Programming node IDs for the home page. The HAR shows these are stable across
# sessions — they're the curated programming for "home", "world", "us", etc.
HOME_PROGRAMMING_IDS = [
    "nyt://programmingnode/8d50cc79-d57b-5218-9103-ba22a1eb4a88",
    "nyt://programmingnode/965f4948-e08d-5c60-9bbf-478f4d40cb7d",
    "nyt://programmingnode/03d72c5c-452a-531f-b187-e94ffbc36635",
]


def get_headlines(
    *,
    limit: int = 25,
    audio_only: bool = False,
    client: Optional[NYTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    """Flat list of headlines extracted from the personalized homes query.

    When `audio_only=True` (default usage for the podcast pipeline), only
    articles that ship a synthetic-narration MP3 are returned.
    """
    client = client or NYTClient()
    cache = cache or Cache()

    payload = _query_homes(
        client,
        cache,
        operation_name="LegacyPersonalizedPackagesQuery",
        sha256_hash=HASH_LEGACY_PERSONALIZED_PACKAGES,
        homes_key="personalizationHomes",
        no_cache=no_cache,
    )

    articles = list(_walk_assets(payload, homes_key="personalizationHomes"))
    if audio_only:
        articles = [a for a in articles if a.get("audio_url")]

    return {
        "schema_version": 1,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "articles": articles[:limit] if limit > 0 else articles,
    }


def _query_homes(
    client: NYTClient,
    cache: Cache,
    *,
    operation_name: str,
    sha256_hash: str,
    homes_key: str,
    no_cache: bool,
) -> dict:
    # Cache key includes the operation + ids so we don't collide between
    # personalized vs generic queries.
    cache_url = f"{client.GRAPHQL}?op={operation_name}&hash={sha256_hash}&homes={homes_key}"
    if not no_cache:
        cached = cache.get_json("GET", cache_url, TTL_HEADLINES)
        if cached is not None:
            return cached
    data = client.graphql(
        operation_name,
        sha256_hash=sha256_hash,
        variables={"ids": HOME_PROGRAMMING_IDS},
        space=False,
    )
    cache.set_json("GET", cache_url, data)
    return data


def _walk_assets(payload: dict, *, homes_key: str) -> Iterator[dict]:
    """Walk personalizationHomes -> personalizedData -> asset, yielding flat dicts."""
    homes = (payload.get("data") or {}).get(homes_key) or []
    seen_uris: set[str] = set()
    for home in homes:
        for entry in (home.get("personalizedData") or []):
            asset = entry.get("asset")
            if not isinstance(asset, dict):
                continue
            if asset.get("__typename") != "Article":
                continue
            uri = asset.get("uri") or asset.get("id")
            if uri and uri in seen_uris:
                continue
            if uri:
                seen_uris.add(uri)
            yield _flatten_asset(asset)


def _flatten_asset(asset: dict) -> dict:
    headline = (asset.get("headline") or {}).get("default")
    bylines = asset.get("bylines") or []
    byline = None
    if bylines:
        byline = bylines[0].get("renderedRepresentation") or None
    section = ((asset.get("section") or {}).get("displayName")
               or (asset.get("section") or {}).get("name"))
    audio_asset = (asset.get("featuredAudio") or {}).get("asset") or {}

    return {
        "uri": asset.get("uri"),
        "url": asset.get("url"),
        "source_id": asset.get("sourceId"),
        "title": headline,
        "byline": byline,
        "section": section,
        "published": asset.get("firstPublished"),
        "audio_url": audio_asset.get("fileUrl"),
        "audio_duration": audio_asset.get("length"),
        "audio_kind": audio_asset.get("audioContentType"),
        "audio_headline": (audio_asset.get("headline") or {}).get("default"),
    }
