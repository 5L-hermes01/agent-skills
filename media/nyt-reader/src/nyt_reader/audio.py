"""Resolve and optionally download a NYT narrated MP3.

Unlike FT (where audio availability requires a separate call), NYT inlines
`featuredAudio.asset.fileUrl` in the headlines and article responses. This
module is a thin wrapper: pull the URL from headlines/article, then download.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from .cache import Cache, TTL_AUDIO
from .client import NYTClient, NotFoundError


def get_audio(
    url_or_uri: str,
    *,
    download: bool = False,
    client: Optional[NYTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    """Resolve audio for an article URL. Optionally download the MP3.

    The audio URL is sourced from the article's __NEXT_DATA__ blob (via
    get_article). For a "do I have audio?" check this means fetching the
    HTML page, which is cheaper than the headlines query but still a real
    request — cached 30d like article body.
    """
    # Lazy import to avoid a circular client/article dep at module load.
    from .article import get_article

    article = get_article(url_or_uri, client=client, cache=cache, no_cache=no_cache)
    out = {
        "url": article.get("url"),
        "uri": article.get("uri"),
        "available": bool(article.get("audio_url")),
        "remote_url": article.get("audio_url"),
        "duration": article.get("audio_duration"),
        "local_path": None,
    }
    if download and out["available"] and out["remote_url"]:
        out["local_path"] = str(
            download_mp3(out["remote_url"], client=client, cache=cache, no_cache=no_cache)
        )
    return out


def download_mp3(
    remote_url: str,
    *,
    client: Optional[NYTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> Path:
    cache = cache or Cache()
    if not no_cache:
        existing = cache.get_bytes_path("GET", remote_url, TTL_AUDIO)
        if existing is not None:
            return existing
    client = client or NYTClient()
    data = client.get_bytes(remote_url, space=False)
    return cache.set_bytes("GET", remote_url, data)
