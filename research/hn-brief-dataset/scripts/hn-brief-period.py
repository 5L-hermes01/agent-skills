#!/usr/bin/env python3
"""hn-brief-period — build a compact corpus for the weekly/monthly aggregators.

Reads the local HN Brief dataset and prints, for a trailing window of days, the
top headlines plus a bounded excerpt of each day's digest. This is the input the
weekly (#hacker-news-weekly) and monthly (#hacker-news-monthly) LLM jobs
summarize — the corpus is built deterministically so the model never has to
parse ~60 KB JSON per day.

Usage
-----
  hn-brief-period.py --days 7                     # weekly corpus
  hn-brief-period.py --days 30 --headlines 12 --digest-chars 1500   # monthly
  hn-brief-period.py --days 7 --json              # machine-readable

The window is the last N published dates ending at the latest date in the
dataset (or --end YYYY-MM-DD). Missing days are noted, never invented.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

DATA_ROOT = Path("/opt/shared_space/hn-brief-data")
NY = ZoneInfo("America/New_York")


def load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def day_path(date: str) -> Path:
    y, m, d = date.split("-")
    return DATA_ROOT / "daily" / y / m / f"{d}.json"


def domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def hn_link(story: dict) -> str:
    return f"https://news.ycombinator.com/item?id={story['id']}"


def build(days: int, end: str | None, headlines: int, digest_chars: int) -> dict:
    archive = load_json(DATA_ROOT / "archive.json")
    assert isinstance(archive, list)
    dates = sorted({e["date"] for e in archive})
    if end:
        dates = [d for d in dates if d <= end]
    window = dates[-days:]
    days_out = []
    for date in window:
        path = day_path(date)
        if not path.exists():
            days_out.append({"date": date, "missing": True})
            continue
        day = load_json(path)
        assert isinstance(day, dict)
        stories = day.get("stories", [])[:headlines]
        digest = (day.get("digest") or "").strip()
        days_out.append({
            "date": date,
            "path": str(path),
            "storyCount": (day.get("quality") or {}).get("storyCount"),
            "stories": [
                {"rank": i, "title": s["title"], "domain": domain(s["url"]),
                 "points": s["points"], "comments": s.get("num_comments", 0),
                 "url": s["url"], "hn": hn_link(s)}
                for i, s in enumerate(stories, 1)
            ],
            "digest": digest[:digest_chars] + (" …" if len(digest) > digest_chars else ""),
            "digestFullChars": len(digest),
        })
    return {"days": days_out, "window": {"count": len(window), "first": window[0] if window else None,
                                         "last": window[-1] if window else None}}


def cache_target(label: str, last_date: str | None) -> str:
    """Deterministic output path for the aggregator's own digest."""
    if not last_date:
        return ""
    y, m, d = (int(x) for x in last_date.split("-"))
    if label == "monthly":
        return f"/opt/data/cache/hn-brief/monthly/{y:04d}-{m:02d}.md"
    iso = datetime(y, m, d).isocalendar()
    return f"/opt/data/cache/hn-brief/weekly/{iso.year:04d}-W{iso.week:02d}.md"


def render(doc: dict, days: int, label: str) -> str:
    w = doc["window"]
    target = cache_target(label, w["last"])
    out = [
        f"HN BRIEF {label.upper()} CORPUS — last {days} days",
        f"window: {w['first']} … {w['last']}  ({w['count']} published date(s) in the dataset)",
        f"save_to: {target}",
        "This is the raw material: top headlines per day + a bounded excerpt of each day's digest.",
        "Every story line carries its OWN article URL and its OWN HN discussion URL.",
        "Use them verbatim, exactly as given — never invent, shorten, or reuse a URL from another story.",
        "",
    ]
    for day in doc["days"]:
        if day.get("missing"):
            out += [f"=== {day['date']} === (MISSING — no dataset file; do not invent content)", ""]
            continue
        out.append(f"=== {day['date']} === ({day.get('storyCount')} stories)")
        out.append("HEADLINES")
        for s in day["stories"]:
            out.append(f"  {s['rank']}. {s['title']} ({s['domain']}) "
                       f"{s['points']} pts, {s['comments']} cmts")
            out.append(f"      article: {s['url']}")
            out.append(f"      hn: {s['hn']}")
        out.append("")
        out.append(f"DAILY DIGEST ({day.get('digestFullChars')} chars"
                   f"{', excerpted' if day['digest'].endswith('…') else ''})")
        out.append(day["digest"] or "(no digest)")
        out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a weekly/monthly HN Brief corpus")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--label", choices=["weekly", "monthly"], default=None,
                    help="aggregator label; also selects the weekly/monthly cache path")
    ap.add_argument("--end", help="last date to include (YYYY-MM-DD); default = latest")
    ap.add_argument("--headlines", type=int, default=20)
    ap.add_argument("--digest-chars", type=int, default=3000)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    label = args.label or ("monthly" if args.days > 14 else "weekly")

    if not DATA_ROOT.exists():
        sys.exit(f"dataset root {DATA_ROOT} is not mounted")
    doc = build(args.days, args.end, args.headlines, args.digest_chars)
    if args.json:
        doc["label"] = label
        doc["save_to"] = cache_target(label, doc["window"]["last"])
        print(json.dumps(doc, indent=2))
    else:
        print(render(doc, args.days, label))


if __name__ == "__main__":
    main()
