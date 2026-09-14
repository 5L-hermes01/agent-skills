"""`waytoagi` CLI entrypoint."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, archive
from .blocks import find_first_mention
from .bootstrap import extract_blocks
from .cache import CacheMode, cached_fetch
from .client import fetch_html
from .update_log import render

DEFAULT_URL = "https://waytoagi.feishu.cn/wiki/QPe5w5g7UisbEkkow8XcDmOpn8e?with_guest=1"
DEFAULT_HEADING = "近 7 日更新日志"
ARCHIVE_NEEDLE = "历史更新"

EXIT_OK = 0
EXIT_NOT_FOUND = 3
EXIT_TRANSIENT = 4
EXIT_UPSTREAM_CONTRACT = 5


def _resolve_archive_url(main_blocks: dict) -> str | None:
    mention = find_first_mention(main_blocks, ARCHIVE_NEEDLE)
    if not mention or not mention.get("url"):
        return None
    url = mention["url"]
    # Ensure guest-mode parameter is present.
    return url if "with_guest=1" in url else url + ("&" if "?" in url else "?") + "with_guest=1"


def _fetch_and_extract(url: str, cache_mode: CacheMode) -> dict:
    res = cached_fetch(url, fetcher=fetch_html, mode=cache_mode)
    label = "cache" if res.hit else "fetch"
    age = f" age={res.age_seconds:.0f}s" if res.hit else ""
    print(f"[info] {label} {url} ({len(res.body)} bytes{age})", file=sys.stderr)
    blocks = extract_blocks(res.body)
    print(f"[info] {len(blocks)} blocks parsed", file=sys.stderr)
    return blocks


def _cmd_update_log(args) -> int:
    cache_mode: CacheMode = (
        "no" if args.no_cache else "refresh" if args.refresh else "read+write"
    )
    main_blocks = _fetch_and_extract(args.url, cache_mode)
    if not main_blocks:
        print("[err] no blocks parsed — SSR contract may have changed", file=sys.stderr)
        return EXIT_UPSTREAM_CONTRACT

    if args.emit_raw_blocks and not args.archive:
        json.dump(main_blocks, sys.stdout, ensure_ascii=False, indent=2)
        return EXIT_OK

    if args.archive:
        archive_url = _resolve_archive_url(main_blocks)
        if not archive_url:
            print(f"[err] could not find a {ARCHIVE_NEEDLE!r} mention in the main doc", file=sys.stderr)
            return EXIT_NOT_FOUND
        archive_blocks = _fetch_and_extract(archive_url, cache_mode)
        if not archive_blocks:
            print("[err] no archive blocks parsed", file=sys.stderr)
            return EXIT_UPSTREAM_CONTRACT
        if args.emit_raw_blocks:
            json.dump(archive_blocks, sys.stdout, ensure_ascii=False, indent=2)
            return EXIT_OK
        out = archive.render(archive_blocks, source_url=archive_url)
    else:
        out = render(main_blocks, heading=args.heading, source_url=args.url, fuzzy=args.fuzzy)

    if not out["found"]:
        print(f"[err] heading not found: {args.heading!r}", file=sys.stderr)
        return EXIT_NOT_FOUND
    if not out["days"]:
        print("[err] heading found but section is empty", file=sys.stderr)
        return EXIT_UPSTREAM_CONTRACT

    if args.date:
        out["days"] = [d for d in out["days"] if d.get("heading") and args.date in d["heading"]]
    if any(day.get("missing_child_ids") for day in out["days"]):
        print("[err] retained days reference absent blocks — refusing incomplete output", file=sys.stderr)
        return EXIT_UPSTREAM_CONTRACT
    if args.flatten:
        items = []
        for d in out["days"]:
            for it in d.get("items", []):
                items.append({**it, "day": d.get("heading"), "day_heading_id": d.get("heading_id")})
        out = {
            "schema_version": 1,
            "source_url": out["source_url"],
            "heading": out["heading"],
            "heading_id": out["heading_id"],
            "items": items,
        }

    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="waytoagi", description=__doc__)
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("update-log", help="Fetch and render the WaytoAGI daily update log.")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--heading", default=DEFAULT_HEADING,
                   help="Section heading text to match (normalized; emoji-tolerant). Exact match by default.")
    p.add_argument("--fuzzy", action="store_true",
                   help="Fall back to substring matching on the heading when exact-normalized match fails.")
    p.add_argument("--date", help="Filter to one day by substring match on the day heading (e.g. '6 月 18 日').")
    p.add_argument("--flatten", action="store_true", help="Emit a flat items[] list instead of days[].")
    p.add_argument("--archive", action="store_true",
                   help="Render the full '历史更新' archive doc instead of the 7-day section.")
    p.add_argument("--no-cache", action="store_true", help="Bypass cache read+write.")
    p.add_argument("--refresh", action="store_true", help="Bypass cache read; refresh stored entry.")
    p.add_argument("--emit-raw-blocks", action="store_true",
                   help="Dump the raw parsed block dict (debugging).")
    p.set_defaults(func=_cmd_update_log)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:  # noqa: BLE001
        print(f"[err] {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_TRANSIENT


if __name__ == "__main__":
    sys.exit(main())
