"""MyFT saved-articles list and optional audio download."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from .audio import download_mp3
from .cache import Cache, TTL_MYFT
from .client import FTClient


def _myft_url(limit: int) -> str:
    return f"{FTClient.APP_API}/myft/content/v1?limit={limit}"


def get_myft(
    *,
    limit: int = 50,
    download_audio: bool = False,
    client: Optional[FTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    url = _myft_url(limit)
    cache = cache or Cache()
    raw = None if no_cache else cache.get_json("GET", url, TTL_MYFT)
    if raw is None:
        client = client or FTClient()
        raw = client.get_json(url, space=False)
        cache.set_json("GET", url, raw)

    # MyFT returns a top-level array. Some legacy code might wrap as {content: [...]}.
    items = raw if isinstance(raw, list) else raw.get("content", [])

    out_items: list[dict] = []
    for item in items:
        audio_meta = item.get("audio") or {}
        entry = {
            "uuid": item.get("id"),
            "title": item.get("title"),
            "standfirst": item.get("standfirst"),
            "url": item.get("url"),
            "saved_date": item.get("savedDate"),
            "published": item.get("publishedDate"),
            "audio_available": bool(audio_meta.get("haveFile")),
            "audio_url": audio_meta.get("url"),
            "audio_duration": (audio_meta.get("duration") or {}).get("humantime"),
            "audio_local_path": None,
        }
        if download_audio and entry["audio_available"] and entry["audio_url"]:
            client = client or FTClient()
            entry["audio_local_path"] = str(
                download_mp3(entry["uuid"], entry["audio_url"],
                             client=client, cache=cache, no_cache=no_cache)
            )
        out_items.append(entry)

    return {
        "schema_version": 1,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(out_items),
        "items": out_items,
    }
