"""Single-article fetch via __NEXT_DATA__.

The article page returns a Next.js bundle with the full article model at
`props.pageProps.articleData`. Includes `id` (WP-WSJ-XXX) — the key the
`read-to-me` audio resolver needs.
"""
from __future__ import annotations
from typing import Optional

from ._next_data import extract_next_data, page_props
from .cache import Cache, TTL_ARTICLE
from .client import NotFoundError, WSJClient


def get_article(
    url: str,
    *,
    client: Optional[WSJClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    cache = cache or Cache()
    if not no_cache:
        cached = cache.get_json("GET", url, TTL_ARTICLE)
        if cached is not None:
            return _normalize(cached, url=url)
    client = client or WSJClient()
    html = client.get_html(url)
    payload = extract_next_data(html, url=url)
    cache.set_json("GET", url, payload)
    return _normalize(payload, url=url)


def _normalize(payload: dict, *, url: str) -> dict:
    art = (page_props(payload).get("articleData") or {})
    if not art:
        raise NotFoundError(f"No articleData in __NEXT_DATA__ for {url}")
    tracking = art.get("articleTrackingMeta") or {}
    # WP-WSJ-* id lives on tracking metadata or `originId` — NOT on `id` (a UUID).
    article_id = (
        tracking.get("articleId")
        or art.get("originId")
        or art.get("upstreamOriginId")
    )
    article_type_node = art.get("articleType")
    article_type_name = _name_of(article_type_node)
    return {
        "url": art.get("canonicalUrl") or url,
        "article_id": article_id,
        "headline": _flatten_text(art.get("headline")) or tracking.get("articleHeadline"),
        "flashline": _flatten_text(art.get("flashline")) or _flatten_text(art.get("mobileFlashline")),
        "summary": _first_summary(art.get("flattenedAltSummaries")),
        "byline": _flatten_byline(art.get("byline")) or tracking.get("articleAuthor"),
        "section": article_type_name or _flatten_text(art.get("columnName")),
        "published": (
            tracking.get("articlePublish")
            or tracking.get("articlePublishOrig")
            or art.get("liveDateTimeUtc")
        ),
        "article_type": article_type_name,
        "body": art.get("flattenedBody") or art.get("articleBody"),
    }


def _name_of(value) -> Optional[str]:
    """WSJ wraps articleType as either a string or a `{name, type, parameters}` dict."""
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            return name
    return None


def _flatten_text(value) -> Optional[str]:
    """Coerce WSJ's `{text: "..."}` or list-of-phrases shapes to a flat string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        t = value.get("text")
        if isinstance(t, str):
            return t or None
        return None
    if isinstance(value, list):
        parts = [p for p in (_flatten_text(item) for item in value) if p]
        return "".join(parts) or None
    return None


def _flatten_byline(value) -> Optional[str]:
    """WSJ byline is a list of phrase nodes; concatenate their .text fields."""
    if not value:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        return "".join(
            (item.get("text") or "") for item in value if isinstance(item, dict)
        ).strip() or None
    return _flatten_text(value)


def _first_summary(value) -> Optional[str]:
    """Walk WSJ's nested summary structure to find the first text bullet."""
    if not value:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        for item in value:
            s = _first_summary(item)
            if s:
                return s
        return None
    if isinstance(value, dict):
        # Several shapes seen in the wild:
        # - {text: "..."}
        # - {summary: "..."}
        # - {flattened: {text: "..."}}
        # - {list: {listContent: [{textAndDecorations: {flattened: {text: "..."}}}, ...]}}
        if isinstance(value.get("text"), str) and value["text"].strip():
            return value["text"]
        if isinstance(value.get("summary"), str) and value["summary"].strip():
            return value["summary"]
        for nested_key in ("flattened", "textAndDecorations"):
            nested = value.get(nested_key)
            if nested:
                s = _first_summary(nested)
                if s:
                    return s
        lst = (value.get("list") or {}).get("listContent")
        if lst:
            s = _first_summary(lst)
            if s:
                return s
    return None
