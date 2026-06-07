"""Audio availability check + MP3 download (cached)."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from .article import coerce_uuid
from .cache import Cache, TTL_AUDIO, TTL_AUDIO_CHECK
from .client import FTClient


def get_audio(
    uuid_or_url: str,
    *,
    download: bool = False,
    client: Optional[FTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    uuid = coerce_uuid(uuid_or_url)
    check_url = f"{FTClient.AUDIO_CHECK}/check/{uuid}"
    cache = cache or Cache()
    client = client or FTClient()

    check = None if no_cache else cache.get_json("GET", check_url, TTL_AUDIO_CHECK)
    if check is None:
        check = client.get_json(check_url, space=False)
        cache.set_json("GET", check_url, check)

    out = {
        "uuid": uuid,
        "available": bool(check.get("haveFile")),
        "remote_url": check.get("url"),
        "duration": (check.get("duration") or {}).get("humantime"),
        "size": check.get("size"),
        "local_path": None,
    }
    if download and out["available"] and out["remote_url"]:
        out["local_path"] = str(download_mp3(uuid, out["remote_url"], client=client, cache=cache, no_cache=no_cache))
    return out


def download_mp3(
    uuid: str,
    remote_url: str,
    *,
    client: Optional[FTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> Path:
    cache = cache or Cache()
    if not no_cache:
        existing = cache.get_bytes_path("GET", remote_url, TTL_AUDIO)
        if existing is not None:
            return existing
    client = client or FTClient()
    data = client.get_bytes(remote_url, space=False)
    return cache.set_bytes("GET", remote_url, data)
