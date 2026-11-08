#!/usr/bin/env python3
"""
Fetch the latest full AINews (smol.ai) dispatch for the daily AI news digest.

Why this exists / what changed (2026-08-26):
  - OLD: smol_news_aggregator.py extracted only each item's RSS <description>
    (~300-char condensed blurb) within a fixed N-day calendar window. That
    (a) truncated the actual dispatch — the real issue page is ~48k chars —
    and (b) frequently returned NOTHING because smol.ai's weekday digest lags
    a day, so a 1-day window cut off the newest issue.
  - NEW: pick the NEWEST issue in the feed (robust to the lag), fetch its FULL
    content via the jina.ai markdown reader, and emit the proper per-issue URL
    (not /latest) so the summary links to the real dispatch page.

Fallbacks (primary -> secondary -> graceful degradation):
  1. jina.ai reader for the full dispatch markdown.
  2. If jina fails, fall back to the RSS <description> for the issue.
  3. If the feed itself fails, print a clear error (non-zero exit) so the cron
     job surfaces the failure instead of sending an empty digest.

Output (to stdout, consumed by the daily-ai-news cron prompt):
  === AINEWS FULL DISPATCH ===
  Date: <pubDate>
  Title: <title>
  URL: <per-issue-url>
  NOTE: <staleness note, emitted when the newest issue is older than 2 days>
  --- content ---
  <full markdown or RSS description>
"""
import urllib.request
import sys
from datetime import datetime, timezone

RSS_URL = "https://news.smol.ai/rss.xml"
UA = {"User-Agent": "Mozilla/5.0"}

# AINews normally lags one day on weekdays (see docstring). A dispatch published
# >= 2 days ago means the source itself is stale — flag it so the digest doesn't
# masquerade as today's news.
STALE_AGE_DAYS = 2


def fetch(url, timeout=45):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="replace")


def latest_issue():
    """Return (title, link, pubdate, description) of the newest RSS item."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(fetch(RSS_URL))
    except Exception as e:
        print(f"ERROR: Failed to fetch RSS feed: {e}", file=sys.stderr)
        sys.exit(1)

    items = root.findall(".//item")
    if not items:
        print("ERROR: No items found in RSS feed.", file=sys.stderr)
        sys.exit(1)

    best = None
    for it in items:
        pd_str = it.findtext("pubDate")
        if not pd_str:
            continue
        try:
            pd = datetime.strptime(pd_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if best is None or pd > best[0]:
            best = (pd, it.findtext("title"), it.findtext("link"), it.findtext("description"))
    if best is None:
        print("ERROR: No parseable items in RSS feed.", file=sys.stderr)
        sys.exit(1)
    return best


def full_content(link):
    """Full dispatch markdown via jina.ai reader, or None on failure."""
    try:
        return fetch("https://r.jina.ai/" + link)
    except Exception as e:
        print(f"WARN: jina.ai full-content fetch failed ({e}); falling back to RSS description.",
              file=sys.stderr)
        return None


def staleness_note(pubdate):
    """Return a NOTE line if the newest dispatch is stale, else an empty string.

    Uses the feed's pubDate (UTC), compared against now in UTC. A dispatch
    published >= STALE_AGE_DAYS ago means the source hasn't shipped a newer
    issue — the digest will be based on stale data and should say so.
    """
    age_days = (datetime.now(timezone.utc) - pubdate).days
    if age_days < STALE_AGE_DAYS:
        return ""
    date_str = pubdate.strftime("%d %b %Y")
    return (f"NOTE: AINews source is stale — the newest dispatch is from {date_str}"
            f" and no newer issue has been published. This digest reflects the most"
            f" recent available dispatch, not today's news.")


def main():
    pd, title, link, description = latest_issue()
    print("=== AINEWS FULL DISPATCH ===")
    print(f"Date: {pd.strftime('%Y-%m-%d')} ({pd.strftime('%a, %d %b %Y %H:%M:%S GMT')})")
    print(f"Title: {title}")
    print(f"URL: {link}")
    note = staleness_note(pd)
    if note:
        print(note)
    print("--- content ---")
    content = full_content(link)
    if content:
        print(content)
    else:
        print(description or "(no description available)")


if __name__ == "__main__":
    main()
