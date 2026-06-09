"""Shared helper for extracting Next.js `__NEXT_DATA__` JSON from a WSJ HTML page."""
from __future__ import annotations
import json
import re
from typing import Optional

from .client import NotFoundError

# Match the opening of the script tag. The actual JSON is brace-balanced
# from the first '{' after the tag.
_SCRIPT_OPEN_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>',
    re.IGNORECASE,
)


def extract_next_data(html: str, *, url: str) -> dict:
    """Return the parsed `__NEXT_DATA__` JSON. Raises NotFoundError on miss."""
    m = _SCRIPT_OPEN_RE.search(html)
    if not m:
        raise NotFoundError(f"No __NEXT_DATA__ script tag in HTML for {url}")
    blob = _slice_object(html, m.end())
    if blob is None:
        raise NotFoundError(f"No JSON object in __NEXT_DATA__ script for {url}")
    try:
        return json.loads(blob)
    except json.JSONDecodeError as e:
        raise NotFoundError(f"Could not parse __NEXT_DATA__ for {url}: {e}") from e


def _slice_object(html: str, start: int) -> Optional[str]:
    """Return the brace-balanced JSON object starting at or after `start`."""
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


def page_props(payload: dict) -> dict:
    return ((payload.get("props") or {}).get("pageProps") or {})
