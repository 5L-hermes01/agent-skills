"""Print-edition headlines.

Hits `https://www.wsj.com/print-edition/{YYYYMMDD}/frontpage`, extracts
`__NEXT_DATA__.props.pageProps.{articles, articlesBusiness, articlesWorld,
mostPopularData}`, flattens into a single article list grouped by section.

Print editions lag the live site by a day or so. If a given date returns
404 / no articles, the caller can step back one day at a time.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from ._next_data import extract_next_data, page_props
from .cache import Cache, TTL_HEADLINES
from .client import NotFoundError, WSJClient

# The pageProps section keys we know about. Order matters — front is the
# default headline block.
SECTION_KEYS = (
    ("front", "articles"),
    ("business", "articlesBusiness"),
    ("world", "articlesWorld"),
    ("popular", "mostPopularData"),
)


def get_headlines(
    *,
    edition_date: Optional[str] = None,
    section: Optional[str] = None,
    limit: int = 50,
    client: Optional[WSJClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
    max_days_back: int = 7,
) -> dict:
    """Return the print-edition headlines as a flat list grouped by section.

    edition_date in YYYYMMDD. If omitted, walks back from today until a
    valid edition is found (max_days_back).
    """
    client = client or WSJClient()
    cache = cache or Cache()

    if edition_date:
        payload, found_date = _fetch_edition(client, cache, edition_date, no_cache=no_cache)
    else:
        payload, found_date = _fetch_latest(client, cache, max_days_back, no_cache=no_cache)

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
            payload, found = _fetch_edition(client, cache, yyyymmdd, no_cache=no_cache)
        except NotFoundError as e:
            last_err = e
            continue
        # Verify the page actually has articles — WSJ sometimes serves an
        # empty stub on dates with no edition.
        if (page_props(payload).get("articles") or []):
            return payload, found
        last_err = NotFoundError(f"print edition for {yyyymmdd} had no articles")
    raise last_err or NotFoundError("no print edition found within the search window")
