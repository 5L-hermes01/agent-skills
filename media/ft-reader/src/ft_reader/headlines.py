"""Fetch /structure/v14 and hydrate teaser UUIDs into headlines."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from .article import get_article
from .cache import Cache, TTL_HEADLINES
from .client import FTClient, FTError


STRUCTURE_URL = (
    f"{FTClient.APP_API}/structure/v14"
    "?edition=dynamic&region=us&interactiveGraphicSlots=true"
)


def get_structure(
    *,
    client: Optional[FTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    cache = cache or Cache()
    if not no_cache:
        cached = cache.get_json("GET", STRUCTURE_URL, TTL_HEADLINES)
        if cached is not None:
            return cached
    client = client or FTClient()
    data = client.get_json(STRUCTURE_URL, space=False)
    cache.set_json("GET", STRUCTURE_URL, data)
    return data


def _teasers_for_section(section: dict, limit: int) -> list[str]:
    """Collect teaser UUIDs across both slot shapes.

    Home uses slot.storyGroups[].teasers[]; section pages put teasers[]
    directly on the slot. Some sections mix both.
    """
    seen: set[str] = set()
    ordered: list[str] = []

    def _add(uuid: str) -> bool:
        if uuid in seen:
            return False
        seen.add(uuid)
        ordered.append(uuid)
        return len(ordered) >= limit

    for slot in section.get("slots", []) or []:
        for uuid in slot.get("teasers", []) or []:
            if _add(uuid):
                return ordered
        for group in slot.get("storyGroups", []) or []:
            for uuid in group.get("teasers", []) or []:
                if _add(uuid):
                    return ordered
    return ordered


def get_headlines(
    *,
    section: Optional[str] = None,
    limit: int = 5,
    client: Optional[FTClient] = None,
    cache: Optional[Cache] = None,
    no_cache: bool = False,
) -> dict:
    structure = get_structure(client=client, cache=cache, no_cache=no_cache)
    section_ids = structure.get("sectionlist") or []
    if section:
        if section not in section_ids:
            raise ValueError(
                f"Unknown section {section!r}. Known: {', '.join(section_ids[:10])}..."
            )
        section_ids = [section]
    client = client or FTClient()
    cache = cache or Cache()
    sections_out: list[dict] = []
    for sid in section_ids:
        sdata = (structure.get("sections") or {}).get(sid) or {}
        meta = sdata.get("meta") or {}
        teasers = _teasers_for_section(sdata, limit)
        headlines: list[dict] = []
        for uuid in teasers:
            try:
                art = get_article(uuid, client=client, cache=cache, no_cache=no_cache)
            except FTError as e:
                # Tolerate per-article fetch failures so one bad article doesn't
                # blank the whole section. Programming errors propagate.
                headlines.append({"uuid": uuid, "error": str(e)[:200]})
                continue
            headlines.append({
                "uuid": art["uuid"],
                "title": art.get("title"),
                "standfirst": art.get("standfirst"),
                "url": art.get("url"),
                "published": art.get("published"),
                "audio_available": bool((art.get("audio") or {}).get("haveFile")),
            })
        sections_out.append({
            "id": sid,
            "name": meta.get("title") or sid,
            "headlines": headlines,
        })
    return {
        "schema_version": 1,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections_out,
    }
