#!/usr/bin/env python3
"""
Fetch the last 30 days of AINews (smol.ai) daily digests for the monthly AI news digest.

Why this exists / what changed (2026-08-26):
  - OLD: smol_news_monthly.py called smol_news_aggregator.py 30, which read only
    each RSS item's ~300-char <description>. A monthly roundup built on those
    truncated blurbs was shallow — the same truncation bug fixed in the daily
    pipeline.
  - NEW: read the last 30 days of the shared ai-news cache
    (/opt/data/cache/ai-news/YYYY/MM/DD/formatted-digest.txt). The daily job now
    writes full-fidelity digests there, so the monthly synthesizes from 30 days
    of rich daily content instead of 30 RSS blurbs. This is the cache's intended
    purpose (cache feeds weekly/monthly synthesis).

Fallbacks (primary -> secondary -> graceful degradation):
  1. Read the ai-news cache for the last N days (default 30).
  2. If fewer than a minimum number of cache days exist (e.g. fresh install,
     cache ramping), fall back to the RSS aggregator's descriptions so the job
     never sends nothing.
  3. Print a clear non-zero-exit error only if both paths fail.

Output (to stdout, consumed by the monthly-ai-news cron prompt):
  === MONTHLY AI NEWS (from N days of daily cache) ===
  Period: YYYY-MM-DD .. YYYY-MM-DD (N days)
  ...concatenated daily digests...
"""
import os
import sys
from datetime import datetime, timedelta, timezone

CACHE_ROOT = "/opt/data/cache/ai-news"
MIN_CACHE_DAYS = 5  # below this, fall back to RSS descriptions


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


def rss_fallback(days_back):
    """Fallback: truncated RSS descriptions via smol_news_aggregator."""
    try:
        import subprocess
        subprocess.run(["/opt/data/scripts/smol_news_aggregator.py", str(days_back)])
    except Exception as e:
        print(f"ERROR: RSS fallback failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    days_back = 30
    if len(sys.argv) > 1:
        days_back = int(sys.argv[1])

    days = read_cache_days(days_back)

    if len(days) < MIN_CACHE_DAYS:
        print(f"WARN: only {len(days)} cache days found (need >= {MIN_CACHE_DAYS}); "
              f"falling back to RSS descriptions.", file=sys.stderr)
        rss_fallback(days_back)
        return

    period_start = days[0][0]
    period_end = days[-1][0]
    print(f"=== MONTHLY AI NEWS (from {len(days)} days of daily cache) ===")
    print(f"Period: {period_start} .. {period_end} ({len(days)} days)\n")
    for date_str, content in days:
        print(f"--- {date_str} ---")
        print(content)
        print()


if __name__ == "__main__":
    main()
