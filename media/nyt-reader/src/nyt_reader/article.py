"""Single-article fetch via HTML embedded-state extraction.

NYT article pages embed the full article model as a JS-side state blob.
The current pattern is `<script>window.__preloadedData = {...};</script>`.
We also try `__NEXT_DATA__` and `__INITIAL_STATE__` as fallbacks so a
template change on one page doesn't break the whole skill.
"""
from __future__ import annotations
import json
import re
from typing import Any, Optional

from .cache import Cache, TTL_ARTICLE
from .client import NYTClient, NotFoundError

# Recognized inline-state script markers. We split on '</script>' after the
# anchor to avoid non-greedy regex stopping at the first '}' inside the JSON.
_STATE_ANCHORS = (
    'window.__preloadedData = ',
    'window.__preloadedData=',
    'window.__INITIAL_STATE__ = ',
    'window.__INITIAL_STATE__=',
)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.+?)</script>',
    re.DOTALL,
)


def get_article(
    url_or_uri: str,
    *,
    client: Optional[NYTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    url = _coerce_url(url_or_uri)
    cache = cache or Cache()
    if not no_cache:
        cached = cache.get_json("GET", url, TTL_ARTICLE)
        if cached is not None:
            return _normalize(cached, url=url)
    client = client or NYTClient()
    html = client.get_html(url)
    payload = _extract_next_data(html, url=url)
    cache.set_json("GET", url, payload)
    return _normalize(payload, url=url)


def _coerce_url(s: str) -> str:
    s = s.strip()
    if s.startswith("nyt://"):
        # No deterministic URI -> URL mapping without a GraphQL lookup; surface
        # the error so the caller passes the actual article URL.
        raise NotFoundError(
            f"Pass the article URL (https://www.nytimes.com/...), not a nyt:// URI ({s})"
        )
    if s.startswith("/"):
        return f"https://www.nytimes.com{s}"
    if not s.startswith("http"):
        raise NotFoundError(f"Not a valid NYT article URL: {s!r}")
    return s


_UNDEFINED_RE = re.compile(r'([:\[,])\s*undefined\b')


def _extract_next_data(html: str, *, url: str) -> dict:
    last_err: Optional[Exception] = None

    # 1. Inline `window.__preloadedData = {...};</script>` style.
    #    Use brace-balanced extraction (the inner blob may contain literal
    #    `</script>` substrings inside string values), then sanitize JS-isms
    #    like `undefined` that NYT serializes directly.
    for anchor in _STATE_ANCHORS:
        i = html.find(anchor)
        if i < 0:
            continue
        start = i + len(anchor)
        blob = _slice_object(html, start)
        if blob is None:
            continue
        try:
            return json.loads(_sanitize_js(blob))
        except json.JSONDecodeError as e:
            last_err = e

    # 2. Classic Next.js `<script id="__NEXT_DATA__">` blob (pure JSON).
    m = _NEXT_DATA_RE.search(html)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError as e:
            last_err = e

    if last_err:
        raise NotFoundError(f"Could not parse embedded state for {url}: {last_err}") from last_err
    raise NotFoundError(f"No recognized embedded state in HTML for {url}")


def _slice_object(html: str, start: int) -> Optional[str]:
    """Return the brace-balanced JS object starting at `start`. None if no '{' found."""
    n = len(html)
    while start < n and html[start] in " \t\r\n":
        start += 1
    if start >= n or html[start] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(start, n):
        ch = html[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return html[start:j + 1]
    return None


def _sanitize_js(blob: str) -> str:
    """Replace `:undefined` / `[undefined` / `,undefined` with their `null` equivalent.

    Risks rewriting a standalone `undefined` token inside a string literal, but
    that's near-zero in practice for news article metadata.
    """
    return _UNDEFINED_RE.sub(lambda m: f"{m.group(1)}null", blob)


def _normalize(payload: dict, *, url: str) -> dict:
    """Pull the key article fields out of the Next.js model."""
    article = _find_article_node(payload)
    if not article:
        return {
            "url": url,
            "title": None,
            "byline": None,
            "section": None,
            "published": None,
            "body": None,
            "audio_url": None,
            "audio_duration": None,
        }
    headline = (article.get("headline") or {}).get("default") if isinstance(article.get("headline"), dict) else None
    audio_asset = (article.get("featuredAudio") or {}).get("asset") or {}
    body = article.get("body") or {}
    bylines = article.get("bylines") or []
    byline = bylines[0].get("renderedRepresentation") if bylines else None
    return {
        "url": url,
        "uri": article.get("uri"),
        "title": headline,
        "byline": byline,
        "section": (article.get("section") or {}).get("displayName") if isinstance(article.get("section"), dict) else None,
        "published": article.get("firstPublished"),
        "body": body if isinstance(body, dict) else None,
        "audio_url": audio_asset.get("fileUrl"),
        "audio_duration": audio_asset.get("length"),
    }


def _find_article_node(payload: Any, _depth: int = 0) -> Optional[dict]:
    """DFS for the first node whose __typename is 'Article'."""
    if _depth > 12:
        return None
    if isinstance(payload, dict):
        if payload.get("__typename") == "Article":
            return payload
        for v in payload.values():
            found = _find_article_node(v, _depth + 1)
            if found:
                return found
    elif isinstance(payload, list):
        for v in payload:
            found = _find_article_node(v, _depth + 1)
            if found:
                return found
    return None
