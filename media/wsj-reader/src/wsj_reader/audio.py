"""Resolve and optionally download the WSJ narrated MP3 for an article.

Flow:
  1. fetch article page → extract `article_id` (WP-WSJ-XXX) from __NEXT_DATA__
  2. GET video-api/.../find-all-videos?type=read-to-me&query={article_id}
     → response item has `id` (UUID-in-braces) + `formattedCreationDate`
  3. Probe the m.wsj.net CDN to find the actual rendered MP3:
       https://m.wsj.net/audio/{YYYYMMDD}/{uuid-lower}/{seg}/ele-{id-lower}-full.mp3
     where:
       YYYYMMDD ∈ {creation_date, creation_date + 1 day}
         — articles published evening UTC get audio dated the next UTC day
       seg ∈ 1..MAX_SEGMENT_PROBE
         — segment index = audio render version. Late re-renders bump
           the number; the first 206 IS NOT always the canonical one if
           the article was re-narrated, but it's the lowest seg with a
           file size matching the read-to-me duration.

     Public CDN, no auth on the MP3 itself.
"""
from __future__ import annotations
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from .cache import Cache, TTL_AUDIO, TTL_AUDIO_RESOLVE
from .client import NotFoundError, WSJClient

logger = logging.getLogger(__name__)

# Match WSJ article-id format. Captured straight from "article.id" meta tag
# or articleData.id in __NEXT_DATA__.
ARTICLE_ID_RE = re.compile(r"WP-WSJ-\d{7,12}", re.IGNORECASE)

# Probe ceiling for the segment index. Per HAR observation segment counts top
# out below 20 even for heavily re-narrated articles; 16 is a safe cap with
# plenty of headroom.
MAX_SEGMENT_PROBE = 16

# Tolerance for matching the probed segment's byte size to the expected
# duration. WSJ MP3s are 128 kbps mono, so bytes ≈ duration * 128_000 / 8.
# Within ±10% we accept the segment as the canonical render.
BITRATE_BPS = 128_000
SIZE_MATCH_TOLERANCE = 0.10

# Audio CDN. Public.
AUDIO_CDN = "https://m.wsj.net/audio"


def resolve_audio_for_id(
    article_id: str,
    *,
    client: Optional[WSJClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
    article_url: Optional[str] = None,
) -> dict:
    """Resolve audio metadata + constructed MP3 URL from just a WP-WSJ-* id.

    No HTML fetch, no Cookie required. Used by both `get_audio()` and the
    GraphQL headlines path, so we keep the construction logic in one place.

    Returns dict with: article_id, available, remote_url, duration, byline,
    audio_uuid. Caller may add download/local_path.
    """
    client = client or WSJClient()
    cache = cache or Cache()
    article_id = article_id.upper().strip()
    resolve_url = (
        f"{WSJClient.AUDIO_RESOLVE}?"
        f"{urlencode({'type': 'read-to-me', 'query': article_id})}"
    )
    payload = None if no_cache else cache.get_json("GET", resolve_url, TTL_AUDIO_RESOLVE)
    if payload is None:
        payload = client.get_json(resolve_url, referer=article_url)
        cache.set_json("GET", resolve_url, payload)

    items = payload.get("items") or []
    out = {
        "article_id": article_id,
        "available": False,
        "remote_url": None,
        "duration": None,
        "audio_uuid": None,
        "byline": None,
    }
    if not items:
        return out

    item = items[0]
    out["duration"] = _to_int(item.get("duration"))
    out["byline"] = item.get("author") or None
    uuid = _strip_braces(item.get("id") or "")
    creation_date = _date_from_formatted(item.get("formattedCreationDate"))
    if uuid and creation_date and article_id:
        out["audio_uuid"] = uuid.lower()
        # Find the actual rendered file on the CDN. The path date and segment
        # index are both unreliable from read-to-me metadata alone, so probe.
        probe_url = _probe_cdn(
            client=client,
            cache=cache,
            article_id=article_id,
            uuid=uuid.lower(),
            creation_date=creation_date,
            expected_duration_s=out["duration"],
            no_cache=no_cache,
        )
        if probe_url:
            out["available"] = True
            out["remote_url"] = probe_url
    return out


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
    article_id, article_url = _resolve_article_id(
        url_or_id, client=client, cache=cache, no_cache=no_cache,
    )
    resolved = resolve_audio_for_id(
        article_id, client=client, cache=cache, no_cache=no_cache,
        article_url=article_url,
    )
    out = {
        "article_id": resolved["article_id"],
        "article_url": article_url,
        "available": resolved["available"],
        "remote_url": resolved["remote_url"],
        "duration": resolved["duration"],
        "local_path": None,
    }
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


def _date_from_formatted(date_str: Optional[str]) -> Optional[datetime]:
    """Parse the WSJ 'M/D/YYYY h:mm:ss AM' format → datetime (naive)."""
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _yyyymmdd(date_str: Optional[str]) -> Optional[str]:
    """Kept for backwards-compat with prior call sites."""
    d = _date_from_formatted(date_str)
    return d.strftime("%Y%m%d") if d else None


def _expected_size_bytes(duration_s: Optional[int]) -> Optional[int]:
    if not duration_s or duration_s <= 0:
        return None
    return int(duration_s * BITRATE_BPS / 8)


def _size_matches(actual: int, expected: Optional[int]) -> bool:
    if not expected:
        # No expected size → accept any non-trivial file.
        return actual > 8 * 1024
    return abs(actual - expected) / expected <= SIZE_MATCH_TOLERANCE


def _probe_cdn(
    *,
    client: WSJClient,
    cache: Cache,
    article_id: str,
    uuid: str,
    creation_date: datetime,
    expected_duration_s: Optional[int],
    no_cache: bool,
) -> Optional[str]:
    """Find the real m.wsj.net MP3 URL by probing (date, segment) variants.

    Audio rendering trails article publication by minutes to hours; for
    articles published evening UTC the render lands on the next UTC day,
    so the path date isn't necessarily the article date. Render version
    (segment index) is also unstable across re-narrations.

    Order of probes:
      for d in (pub_date, pub_date + 1):
        for seg in 1..MAX_SEGMENT_PROBE:
          if Range-200 and size matches expected → use it
          if Range-200 and size DOESN'T match → remember as fallback
          if 403 and we previously saw a 206 at lower seg → stop probing
                                                             this date
      → return the best size-matching URL across all probes, or any
        valid one if no size match was found.

    Probes are HTTP Range bytes=0-7 (8 bytes returned). Per-probe latency
    on a warm CDN is <100ms. Result is cached 30d in the WSJ cache so
    daily re-runs make zero probe calls.
    """
    slug = f"ele-{article_id.lower()}-full"
    expected_bytes = _expected_size_bytes(expected_duration_s)

    cache_key = (
        f"{AUDIO_CDN}/_probe/{article_id}/{uuid}/"
        f"{creation_date.strftime('%Y%m%d')}/{expected_duration_s or 0}"
    )
    if not no_cache:
        cached = cache.get_json("GET", cache_key, TTL_AUDIO_RESOLVE)
        if cached is not None:
            return cached or None  # cached "" means "we probed and nothing existed"

    best_match: Optional[tuple[str, int, int]] = None  # (url, size, |Δ|)
    found_url: Optional[str] = None

    for offset_days in (0, 1):
        date_v = (creation_date + timedelta(days=offset_days)).strftime("%Y%m%d")
        base = f"{AUDIO_CDN}/{date_v}/{uuid}"
        seen_206_this_date = False
        for seg in range(1, MAX_SEGMENT_PROBE + 1):
            url = f"{base}/{seg}/{slug}.mp3"
            status, size = _probe_one(client, url)
            if status == 206 and size:
                seen_206_this_date = True
                if _size_matches(size, expected_bytes):
                    # Best possible: exact-match canonical segment.
                    found_url = url
                    logger.debug(
                        "WSJ audio probe matched %s seg=%d size=%d (~%ds expected=%ds)",
                        date_v, seg, size, int(size * 8 / BITRATE_BPS), expected_duration_s,
                    )
                    break
                # Otherwise remember the closest by absolute size delta.
                delta = abs(size - expected_bytes) if expected_bytes else 0
                if not best_match or delta < best_match[2]:
                    best_match = (url, size, delta)
            elif status == 403 and seen_206_this_date:
                # The CDN returned 403 after a run of 206s on this date —
                # we've walked past the last valid segment.
                break
        if found_url:
            break

    resolved = found_url or (best_match[0] if best_match else "")
    cache.set_json("GET", cache_key, resolved)
    if not resolved:
        logger.debug(
            "WSJ audio probe found nothing for %s on (%s, %s)",
            article_id, creation_date.strftime("%Y%m%d"),
            (creation_date + timedelta(days=1)).strftime("%Y%m%d"),
        )
        return None
    return resolved


def _probe_one(client: WSJClient, url: str) -> tuple[int, Optional[int]]:
    """Range-request the first 8 bytes; return (status, total_size_or_None)."""
    try:
        # Lean directly on requests so we can capture Content-Range without
        # going through our normal _raise_for_status path (which would treat
        # 403 as a hard error).
        r = client.session.get(
            url,
            headers={
                "User-Agent": client.user_agent,
                "Range": "bytes=0-7",
            },
            timeout=15,
        )
        client._fetch_count += 1
        if r.status_code == 206:
            cr = r.headers.get("Content-Range", "")
            if "/" in cr:
                total = int(cr.split("/")[-1])
                return 206, total
            return 206, None
        return r.status_code, None
    except Exception as e:
        logger.debug("probe error %s: %s", url, e)
        return 0, None


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
