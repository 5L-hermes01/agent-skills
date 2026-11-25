#!/usr/bin/env python3
"""hn-brief-data — reader for the local HN Brief daily dataset.

Data root: /opt/shared_space/hn-brief-data (read-only, written by a pipeline on
lunarBeacon daily ~07:13 America/New_York).

Subcommands
-----------
  latest                        latest.json + today's top headlines
  top N [--date D]              top N headlines for a date (default: latest)
  search QUERY [--days N]       search titles/summaries/discussions, last N days
  day D [--full]                stories for date D (D = YYYY-MM-DD)
  digest [--date D]             the long-form digest essay
  days                          list published dates from archive.json

All commands print human-readable text unless --json is passed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_ROOT = Path("/opt/shared_space/hn-brief-data")
NY = ZoneInfo("America/New_York")


def ny_today() -> str:
    return datetime.now(NY).strftime("%Y-%m-%d")


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def latest_meta() -> dict:
    return load_json(DATA_ROOT / "latest.json")


def day_path(date: str) -> Path:
    y, m, d = date.split("-")
    return DATA_ROOT / "daily" / y / m / f"{d}.json"


def load_day(date: str | None = None) -> dict:
    if date is None:
        date = latest_meta()["date"]
    assert isinstance(date, str)
    path = day_path(date)
    if not path.exists():
        sys.exit(f"no dataset for {date} ({path} missing)")
    return load_json(path)


def archive() -> list[dict]:
    entries = load_json(DATA_ROOT / "archive.json")
    assert isinstance(entries, list)
    return entries


def hn_link(story: dict) -> str:
    return f"https://news.ycombinator.com/item?id={story['id']}"


def staleness_note() -> str | None:
    """Return a warning if the latest run looks late/failed, else None."""
    meta = latest_meta()
    now = datetime.now(NY)
    if meta["date"] != now.strftime("%Y-%m-%d") and now.hour >= 8:
        return (f"WARNING: latest.json date is {meta['date']} but it is now "
                f"{now:%Y-%m-%d %H:%M %Z} — today's run may have failed. Do not guess today's news.")
    return None


def fmt_story(idx: int, s: dict) -> str:
    return (f"{idx}. {s['title']} ({s['points']} points, {s.get('num_comments', 0)} comments)\n"
            f"   {s['url']}\n"
            f"   HN: {hn_link(s)}")


def cmd_latest(args) -> None:
    meta = latest_meta()
    day = load_day(meta["date"])
    if args.json:
        print(json.dumps({"latest": meta, "quality": day.get("quality"),
                          "stories": day["stories"]}, indent=2))
        return
    warn = staleness_note()
    if warn:
        print(warn + "\n")
    print(f"HN Brief {meta['date']} (run {meta['runId']})")
    q = day.get("quality", {})
    print(f"stories: {q.get('storyCount')} | digestValid: {q.get('digestValid')} | "
          f"storyFailures: {q.get('storyFailures')}")
    print(f"generated: {day.get('generatedAt')}\n")
    for i, s in enumerate(day["stories"], 1):
        print(fmt_story(i, s))


def cmd_top(args) -> None:
    day = load_day(args.date)
    stories = day["stories"][:args.n]
    if args.json:
        print(json.dumps(stories, indent=2))
        return
    print(f"HN Brief {day['date']} — top {len(stories)}")
    for i, s in enumerate(stories, 1):
        print(fmt_story(i, s))


def cmd_search(args) -> None:
    q = args.query.lower()
    cutoff = (datetime.now(NY) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    hits = []
    for entry in archive():
        date = entry["date"]
        if date < cutoff:
            continue
        try:
            day = load_day(date)
        except SystemExit:
            continue
        for rank, s in enumerate(day["stories"], 1):
            blob = " ".join(str(s.get(k) or "") for k in
                            ("title", "url", "summary", "discussion_summary")).lower()
            if q in blob:
                hits.append((date, rank, s))
    if args.json:
        print(json.dumps([{"date": d, "rank": r, "story": s} for d, r, s in hits], indent=2))
        return
    if not hits:
        print(f"no matches for {args.query!r} in the last {args.days} days")
        return
    print(f"{len(hits)} match(es) for {args.query!r} in the last {args.days} days\n")
    for date, rank, s in hits:
        print(f"[{date}] #{rank}: {s['title']} ({s['points']} points)")
        print(f"   {s['url']}")
        print(f"   HN: {hn_link(s)}")
        if args.snippets:
            text = (s.get("summary") or "")
            pos = text.lower().find(q)
            if pos >= 0:
                print(f"   …{text[max(0, pos-140):pos+240].strip()}…")
        print()


def cmd_day(args) -> None:
    day = load_day(args.date)
    if args.json:
        print(json.dumps(day, indent=2))
        return
    print(f"HN Brief {day['date']} — {len(day['stories'])} stories (generated {day.get('generatedAt')})")
    for i, s in enumerate(day["stories"], 1):
        print(fmt_story(i, s))
        if args.full:
            print(f"   Article: {s.get('summary')}")
            print(f"   Discussion: {s.get('discussion_summary')}")
        print()


def cmd_digest(args) -> None:
    day = load_day(args.date)
    print(day.get("digest") or "(no digest)")


def cmd_days(args) -> None:
    for entry in archive():
        print(f"{entry['date']}  {entry.get('storyCount')} stories  run {entry.get('runId')}")


def main() -> None:
    p = argparse.ArgumentParser(description="Read the local HN Brief dataset")
    sub = p.add_subparsers(dest="cmd", required=True)

    def with_json(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
        parser.add_argument("--json", action="store_true", help="machine-readable output")
        return parser

    sp = with_json(sub.add_parser("latest")); sp.set_defaults(func=cmd_latest)

    sp = with_json(sub.add_parser("top")); sp.add_argument("n", type=int)
    sp.add_argument("--date"); sp.set_defaults(func=cmd_top)

    sp = with_json(sub.add_parser("search")); sp.add_argument("query")
    sp.add_argument("--days", type=int, default=7)
    sp.add_argument("--snippets", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = with_json(sub.add_parser("day")); sp.add_argument("date")
    sp.add_argument("--full", action="store_true"); sp.set_defaults(func=cmd_day)

    sp = with_json(sub.add_parser("digest")); sp.add_argument("--date")
    sp.set_defaults(func=cmd_digest)

    sp = with_json(sub.add_parser("days")); sp.set_defaults(func=cmd_days)

    args = p.parse_args()
    if not DATA_ROOT.exists():
        sys.exit(f"dataset root {DATA_ROOT} is not mounted")
    args.func(args)


if __name__ == "__main__":
    main()
