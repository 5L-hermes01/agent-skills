"""WSJ headlines — two transports.

* `via="graphql"` (default): hits shared-data.dowjones.io/gateway/graphql with
  a persisted `summaryCollectionContent` query. Cookie required since mid-2026.
* `via="html"` (legacy): scrapes the print-edition HTML at
  /print-edition/{YYYYMMDD}/frontpage. Body-rich but subject to Datadome
  bot protection and the 24h cookie cycle.

Both transports normalize to the same article schema so downstream code
(data_as_podcasts, agents) doesn't care which path produced the data.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from ._next_data import extract_next_data, page_props
from .audio import resolve_audio_for_id
from .cache import Cache, TTL_HEADLINES
from .client import NotFoundError, WSJClient

# --- HTML (print-edition) ------------------------------------------------

SECTION_KEYS = (
    ("front", "articles"),
    ("business", "articlesBusiness"),
    ("world", "articlesWorld"),
    ("popular", "mostPopularData"),
)

# --- GraphQL (Apollo persisted-query gateway) ----------------------------

SUMMARY_COLLECTION_HASH = (
    "47247cb3777898df3cf6c9b917e200fecc2f16274ef75225a9d9338e190ff4cc"
)
# Collection IDs observed in the WSJ web bundle. Friendly aliases mapped
# to the canonical IDs the GraphQL gateway expects.
COLLECTION_ALIASES = {
    "most-popular": "MOST-POP-WSJ-NO-OPN_1",
    "most-popular-opinion": "MOST-POP-WSJOPINION_1",
    "breaking": "BreakingNews_1",
}
DEFAULT_COLLECTION = "MOST-POP-WSJ-NO-OPN_1"


def get_headlines(
    *,
    via: str = "graphql",
    edition_date: Optional[str] = None,
    section: Optional[str] = None,
    collection: Optional[str] = None,
    limit: int = 50,
    audio_only: bool = False,
    client: Optional[WSJClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
    max_days_back: int = 7,
) -> dict:
    """Top-level headlines dispatcher.

    Args:
      via: "graphql" (default, no auth) or "html" (print-edition scraper).
      edition_date: HTML mode only. YYYYMMDD.
      section: HTML mode only. Filter to one section.
      collection: GraphQL mode only. Friendly name or raw collection ID.
      audio_only: GraphQL mode only. Drop items whose read-to-me returns nothing.
      limit: max articles to return.
    """
    if via == "graphql":
        return _get_headlines_via_graphql(
            collection=collection,
            limit=limit,
            audio_only=audio_only,
            client=client,
            cache=cache,
            no_cache=no_cache,
        )
    if via == "html":
        return _get_headlines_via_html(
            edition_date=edition_date,
            section=section,
            limit=limit,
            client=client,
            cache=cache,
            no_cache=no_cache,
            max_days_back=max_days_back,
        )
    raise ValueError(f"unknown via={via!r}; expected 'graphql' or 'html'")


# ─── GraphQL path ────────────────────────────────────────────────────────


def _get_headlines_via_graphql(
    *,
    collection: Optional[str],
    limit: int,
    audio_only: bool,
    client: Optional[WSJClient],
    cache: Optional[Cache],
    no_cache: bool,
) -> dict:
    client = client or WSJClient()
    cache = cache or Cache()
    collection_id = (
        COLLECTION_ALIASES.get(collection, collection)
        if collection else DEFAULT_COLLECTION
    )

    variables = {
        "articleLimitPerCollection": max(limit, 1) if limit > 0 else 40,
        "flattenCollections": True,
        "summaryCollectionContentId": collection_id,
    }

    cache_url = (
        f"{WSJClient.GRAPHQL_BASE}?op=summaryCollectionContent&col={collection_id}&n="
        f"{variables['articleLimitPerCollection']}"
    )
    payload = None if no_cache else cache.get_json("GET", cache_url, TTL_HEADLINES)
    if payload is None:
        payload = client.graphql_get(SUMMARY_COLLECTION_HASH, variables, space=False)
        cache.set_json("GET", cache_url, payload)

    items = (
        ((payload.get("data") or {}).get("summaryCollectionContent") or {})
        .get("collectionItems") or []
    )

    out: list[dict] = []
    for it in items:
        if limit > 0 and len(out) >= limit:
            break
        normalized = _normalize_graphql_item(it)
        if not normalized:
            continue
        # Resolve audio per article. Tolerate per-item failures.
        try:
            audio = resolve_audio_for_id(
                normalized["article_id"],
                client=client, cache=cache, no_cache=no_cache,
                article_url=normalized["url"],
            )
        except Exception:
            audio = {"available": False, "remote_url": None,
                     "duration": None, "audio_uuid": None, "byline": None}
        if audio_only and not audio["available"]:
            continue
        normalized.update({
            "audio_available": audio["available"],
            "audio_url": audio["remote_url"],
            "audio_duration": audio["duration"],
            "audio_uuid": audio["audio_uuid"],
            "byline": normalized.get("byline") or audio["byline"],
        })
        out.append(normalized)

    return {
        "schema_version": 1,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "via": "graphql",
        "collection_id": collection_id,
        "edition_date": None,
        "articles": out,
    }


def _normalize_graphql_item(item: dict) -> Optional[dict]:
    article_id = item.get("id")
    content = item.get("content") or {}
    url = content.get("sourceUrl")
    if not article_id or not url:
        return None
    flat = content.get("flattenedSummary") or {}
    headline = (flat.get("headline") or {}).get("text")
    mobile = content.get("mobileSummary") or {}
    desc = (((mobile.get("description") or {}).get("content")) or {}).get("text")
    if not desc:
        descs = flat.get("descriptions") or []
        if descs:
            nested = (
                (descs[0].get("textAndDecorations") or {}).get("nested") or []
            )
            if nested:
                desc = nested[0].get("text")
    image_url = None
    images = flat.get("image") or mobile.get("image") or []
    if images:
        src = images[0].get("src") or {}
        if src.get("baseUrl") and src.get("path"):
            image_url = (
                src["baseUrl"].rstrip("/") + "/" + src["path"].lstrip("/")
            )
    return {
        "url": url,
        "article_id": article_id,
        "headline": headline,
        "summary": desc,
        "section": content.get("sectionName"),
        "flashline": flat.get("flashline"),
        "published": content.get("publishedDateTimeUtc"),
        "image_url": image_url,
        "byline": None,
        "breaking_news": bool(content.get("breakingNews")),
    }


# ─── HTML print-edition path (legacy fallback) ───────────────────────────


def _get_headlines_via_html(
    *,
    edition_date: Optional[str],
    section: Optional[str],
    limit: int,
    client: Optional[WSJClient],
    cache: Optional[Cache],
    no_cache: bool,
    max_days_back: int,
) -> dict:
    client = client or WSJClient()
    cache = cache or Cache()

    if edition_date:
        payload, found_date = _fetch_edition(
            client, cache, edition_date, no_cache=no_cache,
        )
    else:
        payload, found_date = _fetch_latest(
            client, cache, max_days_back, no_cache=no_cache,
        )

    pp = page_props(payload)
    out: list[dict] = []
    for section_id, pp_key in SECTION_KEYS:
        if section and section != section_id:
            continue
        items = pp.get(pp_key) or []
        for it in items:
            url = it.get("articleUrl") or it.get("url")
            if not url:
                continue
            out.append({
                "url": url,
                "article_id": None,
                "headline": it.get("headline") or it.get("title"),
                "summary": it.get("summary") or it.get("flashline"),
                "section": section_id,
                "flashline": it.get("flashline"),
                "image_url": it.get("imageUrl"),
                "image_alt": it.get("imageAlt"),
            })
            if limit > 0 and len(out) >= limit:
                break
        if limit > 0 and len(out) >= limit:
            break

    return {
        "schema_version": 1,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "via": "html",
        "collection_id": None,
        "edition_date": found_date,
        "articles": out,
    }


def _print_edition_url(yyyymmdd: str) -> str:
    return f"{WSJClient.BASE}/print-edition/{yyyymmdd}/frontpage"


def _fetch_edition(
    client: WSJClient,
    cache: Cache,
    yyyymmdd: str,
    *,
    no_cache: bool,
) -> tuple[dict, str]:
    url = _print_edition_url(yyyymmdd)
    if not no_cache:
        cached = cache.get_json("GET", url, TTL_HEADLINES)
        if cached is not None:
            return cached, yyyymmdd
    html = client.get_html(url)
    payload = extract_next_data(html, url=url)
    cache.set_json("GET", url, payload)
    return payload, yyyymmdd


def _fetch_latest(
    client: WSJClient,
    cache: Cache,
    max_days_back: int,
    *,
    no_cache: bool,
) -> tuple[dict, str]:
    today = date.today()
    last_err: Optional[Exception] = None
    for back in range(max_days_back + 1):
        d = today - timedelta(days=back)
        yyyymmdd = d.strftime("%Y%m%d")
        try:
            payload, found = _fetch_edition(
                client, cache, yyyymmdd, no_cache=no_cache,
            )
        except NotFoundError as e:
            last_err = e
            continue
        if (page_props(payload).get("articles") or []):
            return payload, found
        last_err = NotFoundError(f"print edition for {yyyymmdd} had no articles")
    raise last_err or NotFoundError(
        "no print edition found within the search window",
    )
