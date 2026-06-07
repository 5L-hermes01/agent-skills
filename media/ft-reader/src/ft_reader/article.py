"""Single-article fetch (cached 30d) and normalization."""
from __future__ import annotations
import re
from typing import Any, Optional

from .cache import Cache, TTL_ARTICLE
from .client import FTClient, NotFoundError

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def coerce_uuid(uuid_or_url: str) -> str:
    m = UUID_RE.search(uuid_or_url.lower())
    if not m:
        raise NotFoundError(f"Could not extract article UUID from {uuid_or_url!r}")
    return m.group(0)


def _normalize(raw: dict, uuid: str) -> dict:
    """Normalize FT's nested article shape into a flat, agent-friendly dict."""
    content = raw.get("data", raw)
    if isinstance(content, dict) and "content" in content:
        content = content["content"]
    out = {
        "uuid": content.get("id") or uuid,
        "title": content.get("title"),
        "standfirst": content.get("standfirst"),
        "byline": _flatten_byline(content.get("byline")),
        "published": content.get("publishedDate") or content.get("firstPublishedDate"),
        "url": content.get("webUrl") or content.get("url"),
        "body": content.get("body"),
        "audio": content.get("audio") or None,
    }
    return out


def _flatten_byline(byline: Any) -> Optional[str]:
    if not byline:
        return None
    if isinstance(byline, str):
        return byline
    # FT byline is a {"tree": {...children: [{type: "author"|"text", ...}]}} shape.
    tree = byline.get("tree") if isinstance(byline, dict) else None
    if not tree:
        return None
    def _text(node):
        if not isinstance(node, dict):
            return ""
        return node.get("value") or node.get("data") or ""

    parts: list[str] = []
    for child in tree.get("children", []):
        if child.get("type") == "author":
            for sub in child.get("children", []):
                parts.append(_text(sub))
        else:
            parts.append(_text(child))
    text = "".join(parts).strip()
    return text or None


def get_article(
    uuid_or_url: str,
    *,
    client: Optional[FTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    uuid = coerce_uuid(uuid_or_url)
    url = f"{FTClient.APP_API}/__content/v4/article/{uuid}?useVanities=false"
    cache = cache or Cache()
    if not no_cache:
        cached = cache.get_json("GET", url, TTL_ARTICLE)
        if cached is not None:
            return _normalize(cached, uuid)
    client = client or FTClient()
    raw = client.get_json(url)
    cache.set_json("GET", url, raw)
    return _normalize(raw, uuid)
