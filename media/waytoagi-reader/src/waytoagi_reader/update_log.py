"""Render the '近 7 日更新日志' section as structured JSON."""
from __future__ import annotations

import sys

from .blocks import (
    block_children,
    block_parent,
    block_type,
    find_heading,
    heading_level,
    render_text,
    split_mention_and_summary,
)


def collect_section(blocks: dict, head_id: str) -> list[str]:
    """Sibling block ids belonging to the heading's section, up to (but not including)
    the next sibling at same-or-shallower heading level."""
    head = blocks[head_id]
    head_level = heading_level(block_type(head)) or 99
    parent = blocks.get(block_parent(head) or "")
    if not parent:
        return []
    siblings = block_children(parent)
    if head_id not in siblings:
        return []
    idx = siblings.index(head_id)
    out: list[str] = []
    for sib_id in siblings[idx + 1:]:
        sib = blocks.get(sib_id)
        if not sib:
            continue
        lvl = heading_level(block_type(sib))
        if lvl is not None and lvl <= head_level:
            break
        out.append(sib_id)
    return out


def _render_item(blocks: dict, bid: str) -> dict:
    b = blocks[bid]
    mention, summary = split_mention_and_summary(b)
    return {
        "id": bid,
        "type": block_type(b),
        "title": mention.get("title") if mention else None,
        "url": mention.get("url") if mention else None,
        "summary": summary or None,
    }


def _render_day(blocks: dict, day_head_id: str) -> dict:
    head = blocks[day_head_id]
    heading_text = render_text(head).strip() or None
    items: list[dict] = []
    referenced = block_children(head)
    missing = [cid for cid in referenced if cid not in blocks]
    for cid in referenced:
        if cid not in blocks:
            continue
        item = _render_item(blocks, cid)
        if item["title"] or item["summary"] or item["type"] in {"image", "divider"}:
            items.append(item)
    if heading_text and not items:
        # Distinguish genuine empties from upstream payload omissions so the
        # operator isn't misled into chasing a phantom encoding bug. Feishu's
        # guest SSR serializes nested block objects only for a recent window of
        # the archive doc; older days reference child ids that are absent from
        # the payload entirely (client-side pagination), so they can't render
        # server-side no matter the parser.
        if missing and len(missing) == len(referenced):
            print(
                f"[warn] day heading {heading_text!r} ({day_head_id}) references "
                f"{len(missing)} child block(s) but NONE are present in the SSR payload — "
                "Feishu omits nested blocks for this (older) part of the archive "
                "(client-side pagination). Content is not recoverable from this HTML; "
                "run with --emit-raw-blocks and confirm the ids are referenced but absent.",
                file=sys.stderr,
            )
        elif missing:
            print(
                f"[warn] day heading {heading_text!r} ({day_head_id}) has {len(missing)} "
                f"of {len(referenced)} child block(s) absent from the SSR payload, and the "
                "remaining present blocks rendered no items.",
                file=sys.stderr,
            )
        else:
            print(
                f"[warn] day heading {heading_text!r} ({day_head_id}) has 0 child blocks "
                "in the SSR payload.",
                file=sys.stderr,
            )
    return {
        "heading_id": day_head_id,
        "heading": heading_text,
        "items": items,
    }


def render(blocks: dict, *, heading: str, source_url: str, fuzzy: bool = False) -> dict:
    """Return the structured update-log dict for the given heading.

    Days are heading-level blocks inside the section; each day's items are the
    children of that day heading. Non-heading blocks that appear directly under
    the section (intro/outro text, dividers) are surfaced under a synthetic
    pre-day with `heading=None`.

    `fuzzy=True` falls back to substring matching when exact-normalized match
    fails — useful when the section heading glyph drifts."""
    head_id = find_heading(blocks, heading, fuzzy=fuzzy)
    if not head_id:
        return {
            "schema_version": 1,
            "source_url": source_url,
            "heading": heading,
            "heading_id": None,
            "found": False,
            "days": [],
        }

    section_ids = collect_section(blocks, head_id)
    days: list[dict] = []
    intro_items: list[dict] = []
    for bid in section_ids:
        b = blocks[bid]
        if heading_level(block_type(b)) is not None:
            day = _render_day(blocks, bid)
            # Drop empty heading-level blocks (Feishu docs commonly carry stray
            # blank heading3 separators with no text and no children).
            if day["heading"] or day["items"]:
                days.append(day)
        else:
            item = _render_item(blocks, bid)
            if item["title"] or item["summary"]:
                intro_items.append(item)
    if intro_items:
        days.insert(0, {"heading_id": None, "heading": None, "items": intro_items})

    return {
        "schema_version": 1,
        "source_url": source_url,
        "heading": render_text(blocks[head_id]),
        "heading_id": head_id,
        "found": True,
        "days": days,
    }
