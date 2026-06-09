"""Resolve and optionally download the WSJ narrated MP3 for an article.

Flow:
  1. fetch article page → extract `article_id` (WP-WSJ-XXX) from __NEXT_DATA__
  2. GET video-api/.../find-all-videos?type=read-to-me&query={article_id}
     → response item has `id` (UUID-in-braces) + `formattedCreationDate`
  3. construct
     https://m.wsj.net/audio/{YYYYMMDD}/{uuid-lower}/1/ele-{id-lower}-full.mp3
     and (optionally) download. Public CDN, no auth on the MP3 itself.
"""
from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from .cache import Cache, TTL_AUDIO, TTL_AUDIO_RESOLVE
from .client import NotFoundError, WSJClient

# Match WSJ article-id format. Captured straight from "article.id" meta tag
# or articleData.id in __NEXT_DATA__.
ARTICLE_ID_RE = re.compile(r"WP-WSJ-\d{7,12}", re.IGNORECASE)


def get_audio(
    url_or_id: str,
    *,
    download: bool = False,
    client: Optional[WSJClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    client = client or WSJClient()
    cache = cache or Cache()
    article_id, article_url = _resolve_article_id(url_or_id, client=client, cache=cache, no_cache=no_cache)

    resolve_url = f"{WSJClient.AUDIO_RESOLVE}?{urlencode({'type': 'read-to-me', 'query': article_id})}"
    payload = None if no_cache else cache.get_json("GET", resolve_url, TTL_AUDIO_RESOLVE)
    if payload is None:
        payload = client.get_json(resolve_url, referer=article_url)
        cache.set_json("GET", resolve_url, payload)

    items = payload.get("items") or []
    out = {
        "article_id": article_id,
        "article_url": article_url,
        "available": False,
        "remote_url": None,
        "duration": None,
        "local_path": None,
    }
    if not items:
        return out

    item = items[0]
    out["duration"] = _to_int(item.get("duration"))
    uuid = _strip_braces(item.get("id") or "")
    creation_date = _yyyymmdd(item.get("formattedCreationDate"))
    if uuid and creation_date and article_id:
        out["available"] = True
        out["remote_url"] = (
            f"https://m.wsj.net/audio/{creation_date}/{uuid.lower()}/1/"
            f"ele-{article_id.lower()}-full.mp3"
        )
    if download and out["available"] and out["remote_url"]:
        out["local_path"] = str(
            download_mp3(out["remote_url"], client=client, cache=cache, no_cache=no_cache)
        )
    return out


def _resolve_article_id(
    url_or_id: str,
    *,
    client: WSJClient,
    cache: Cache,
    no_cache: bool,
) -> tuple[str, Optional[str]]:
    """Return (article_id, article_url-or-None)."""
    s = url_or_id.strip()
    m = ARTICLE_ID_RE.fullmatch(s)
    if m:
        return s.upper(), None
    if not s.startswith("http"):
        raise NotFoundError(
            f"Not a recognized WSJ article URL or WP-WSJ-* id: {url_or_id!r}"
        )
    from .article import get_article
    art = get_article(s, client=client, cache=cache, no_cache=no_cache)
    aid = art.get("article_id")
    if not aid:
        raise NotFoundError(f"No article_id parsed from {s}")
    return aid.upper(), art.get("url") or s


def download_mp3(
    remote_url: str,
    *,
    client: Optional[WSJClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> Path:
    cache = cache or Cache()
    if not no_cache:
        existing = cache.get_bytes_path("GET", remote_url, TTL_AUDIO)
        if existing is not None:
            return existing
    client = client or WSJClient()
    data = client.get_bytes(remote_url, space=False)
    return cache.set_bytes("GET", remote_url, data)


def _strip_braces(s: str) -> str:
    return s.strip("{}").strip()


def _yyyymmdd(date_str: Optional[str]) -> Optional[str]:
    """Parse the WSJ 'M/D/YYYY h:mm:ss AM' format → YYYYMMDD."""
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    return None


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
