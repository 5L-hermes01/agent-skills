#!/usr/bin/env python3
"""
Fetch the last 7 days of AINews (smol.ai) daily digests for the weekly AI news roundup.

Why this exists / what changed (2026-08-26):
  - OLD: fetched the last 7 days of smol.ai RSS items and pulled each issue's
    FULL dispatch (~48k chars each) via jina — ~7 full dispatches (~340KB)
    into context every week. Heavy, and redundant with the daily pipeline.
  - NEW: read the last 7 days of the shared ai-news cache
    (/opt/data/cache/ai-news/YYYY/MM/DD/formatted-digest.txt). The daily job
    writes full-fidelity digests there, so the weekly roundup is built from
    those instead of re-fetching raw dispatches. Consistent with the monthly
    job, and the cache's intended purpose (cache feeds weekly/monthly).

Fallbacks (primary -> secondary -> graceful degradation):
  1. Read the ai-news cache for the last N days (default 7).
  2. If fewer than MIN_CACHE_DAYS (3) cache days exist, fall back to fetching
     full dispatches directly so the job never sends nothing.
  3. Non-zero exit only if both paths fail.

Output (to stdout, consumed by the weekly-ai-news cron prompt):
  === WEEKLY AI NEWS (from N days of daily cache) ===
  Period: YYYY-MM-DD .. YYYY-MM-DD (N days)
  ...concatenated daily digests...
"""
import os
import sys
from datetime import datetime, timedelta, timezone

CACHE_ROOT = "/opt/data/cache/ai-news"
MIN_CACHE_DAYS = 3  # below this, fall back to full-dispatch fetch


def read_cache_days(days_back):
    """Return sorted list of (date_str, content) from the ai-news cache."""
    today = datetime.now(timezone.utc).date()
    results = []
    for i in range(days_back):
        d = today - timedelta(days=i)
        path = os.path.join(CACHE_ROOT, d.strftime("%Y/%m/%d"), "formatted-digest.txt")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    content = f.read().strip()
                if content:
                    results.append((d.strftime("%Y-%m-%d"), content))
            except OSError as e:
                print(f"WARN: could not read cache {path}: {e}", file=sys.stderr)
    results.sort()
    return results


def full_dispatch_fallback(days_back):
    """Fallback: fetch last N days of full dispatches directly."""
    import urllib.request
    import re

    try:
        url = "https://news.smol.ai/rss.xml"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        content = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"ERROR: fallback RSS fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    items = list(re.finditer(r"<item>(.*?)</item>", content, re.DOTALL))
    if not items:
        print("ERROR: No items found in RSS feed.", file=sys.stderr)
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    recent = []
    for m in items[:20]:  # feed is newest-first; cap for safety
        item = m.group(1)
        link_m = re.search(r"<link>(.*?)</link>", item)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
        link = link_m.group(1) if link_m else None
        pub = date_m.group(1) if date_m else ""
        if not link:
            continue
        try:
            cleaned = pub
            if cleaned.endswith("GMT"):
                cleaned = cleaned[:-3].strip()
            cleaned = cleaned.split("+")[0].strip()
            dt = datetime.strptime(cleaned, "%a, %d %b %Y %H:%M:%S").replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                recent.append(link)
        except Exception:
            continue
        if len(recent) >= 7:
            break

    print(f"=== WEEKLY AI NEWS (fallback: {len(recent)} full dispatches) ===\n")
    for link in recent:
        print(f"--- {link} ---")
        try:
            jina = "https://r.jina.ai/" + link
            jreq = urllib.request.Request(jina, headers={"User-Agent": "Mozilla/5.0"})
            print(urllib.request.urlopen(jreq, timeout=45).read().decode("utf-8", errors="replace"))
            print()
        except Exception as e:
            print(f"Extraction failed: {e}\n")


def main():
    days_back = 7
    if len(sys.argv) > 1:
        days_back = int(sys.argv[1])

    days = read_cache_days(days_back)

    if len(days) < MIN_CACHE_DAYS:
        print(f"WARN: only {len(days)} cache days found (need >= {MIN_CACHE_DAYS}); "
              f"falling back to full-dispatch fetch.", file=sys.stderr)
        full_dispatch_fallback(days_back)
        return

    period_start = days[0][0]
    period_end = days[-1][0]
    print(f"=== WEEKLY AI NEWS (from {len(days)} days of daily cache) ===")
    print(f"Period: {period_start} .. {period_end} ({len(days)} days)\n")
    for date_str, content in days:
        print(f"--- {date_str} ---")
        print(content)
        print()


if __name__ == "__main__":
    main()
