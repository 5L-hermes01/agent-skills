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
  NOTE: <note, emitted when the newest issue is older than 2 days OR is the
  same dispatch the previous run already served>
  --- content ---
  <full markdown or RSS description>
"""
import urllib.request
import sys
from datetime import datetime, timezone

RSS_URL = "https://news.smol.ai/rss.xml"
# 2026-09-04: AINews migrated to Latent.Space (news.smol.ai now returns HTTP 402).
# The Latent.Space Substack feed carries the daily [AINews] dispatch as its first
# item. Used as the fallback when the smol.ai feed is unreachable.
LATENT_FEED_URL = "https://www.latent.space/feed"
UA = {"User-Agent": "Mozilla/5.0"}

# AINews normally lags one day on weekdays (see docstring). A dispatch published
# >= 2 days ago means the source itself is stale — flag it so the digest doesn't
# masquerade as today's news.
STALE_AGE_DAYS = 2

# 2026-09-11: A one-day hole in the source (e.g. AINews skips a day) was served
# silently as if fresh — the same dispatch went out two days running with no
# staleness NOTE. Track the last dispatch URL we saw so a repeat is labelled.
STATE_FILE = "/opt/data/cache/ai-news/.last-dispatch.json"


def fetch(url, timeout=45):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="replace")


def _newest_item(xml_text, title_prefix=None):
    """Return (pubdate, title, link, description) of the newest item in XML text,
    optionally restricted to items whose title starts with title_prefix."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)
    best = None
    for it in root.findall(".//item"):
        t = it.findtext("title") or ""
        if title_prefix and not t.startswith(title_prefix):
            continue
        pd_str = it.findtext("pubDate")
        if not pd_str:
            continue
        try:
            pd = datetime.strptime(pd_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if best is None or pd > best[0]:
            best = (pd, t, it.findtext("link"), it.findtext("description"))
    return best


def latest_issue():
    """Return (pubdate, title, link, description) of the newest AINews issue.

    Queries BOTH feeds and keeps whichever has the newest item:
      - news.smol.ai RSS (primary while it publishes)
      - Latent.Space Substack feed (AINews migrated there 2026-09-04), filtered
        to "[AINews]" items

    2026-09-18: smol.ai stopped shipping new dispatches after ~09-10 but its
    feed keeps serving the 09 Sep item with a frozen pubDate. Taking the max
    across both feeds is what makes the digest actually daily again — a
    first-feed-wins fallback served the same stale dispatch for 9 days while
    fresh dispatches were sitting in the Latent.Space feed.
    """
    candidates = []
    for url, prefix, label in ((RSS_URL, None, "smol.ai"),
                               (LATENT_FEED_URL, "[AINews]", "Latent.Space")):
        try:
            item = _newest_item(fetch(url), title_prefix=prefix)
        except Exception as e:
            print(f"WARN: {label} feed fetch failed ({e}).", file=sys.stderr)
            continue
        if item:
            candidates.append(item)

    if not candidates:
        print("ERROR: No parseable AINews items in any feed.", file=sys.stderr)
        sys.exit(1)

    best = max(candidates, key=lambda x: x[0])
    if best[2] and "latent.space" in best[2]:
        print("INFO: newest dispatch is on Latent.Space (smol.ai feed stale).",
              file=sys.stderr)
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


def repeat_note(link, pubdate):
    """Return a NOTE line if this is the same dispatch the previous run saw.

    Reads the one-line state file written by the previous run. Never raises —
    a missing/corrupt state file just means "cannot tell", and the digest is
    served as usual. The state file is updated by record_dispatch() AFTER the
    note is computed, so a run always compares against the run before it.
    """
    try:
        import json
        with open(STATE_FILE) as f:
            prev = json.load(f)
    except Exception:
        return ""
    prev_link = (prev or {}).get("link")
    if prev_link and prev_link == link:
        date_str = pubdate.strftime("%d %b %Y")
        return (f"NOTE: AINews has not published a new dispatch — the newest issue"
                f" is the same {date_str} dispatch covered in the previous digest."
                f" This digest reflects the most recent available dispatch, not"
                f" today's news.")
    return ""


def record_dispatch(link, pubdate):
    """Record the dispatch we just served so the next run can spot a repeat.

    Best-effort: any failure is non-fatal and never breaks the digest.
    """
    try:
        import json, os
        tmp = STATE_FILE + ".tmp"
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump({"link": link, "pubdate": pubdate.strftime("%Y-%m-%d")}, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        print(f"WARN: could not record dispatch state ({e}).", file=sys.stderr)


def main():
    pd, title, link, description = latest_issue()
    print("=== AINEWS FULL DISPATCH ===")
    print(f"Date: {pd.strftime('%Y-%m-%d')} ({pd.strftime('%a, %d %b %Y %H:%M:%S GMT')})")
    print(f"Title: {title}")
    print(f"URL: {link}")
    for note in (staleness_note(pd), repeat_note(link, pd)):
        if note:
            print(note)
    record_dispatch(link, pd)
    print("--- content ---")
    content = full_content(link)
    if content:
        print(content)
    else:
        print(description or "(no description available)")


if __name__ == "__main__":
    main()
