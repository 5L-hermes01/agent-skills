#!/usr/bin/env python3
"""
Daily X/Twitter signal delivery script.
Fetches tweets from the AI High Signal list, caches raw + links output,
and produces a clean daily digest. Deterministic — no LLM involved.

Called by cron job 7c85dd238709 (no_agent mode). Stdout = delivery.
"""
import subprocess, sys, os, json
from datetime import datetime, timezone
from pathlib import Path

LIST_ID = "1585430245762441216"
MAX_TWEETS = 50
CACHE_ROOT = Path("/opt/data/cache/xdigest")
SCRIPTS = Path("/opt/data/scripts")
XDIGEST = SCRIPTS / "xdigest_fetch.py"

def run(cmd, timeout=120):
    """Run a command, return (stdout, success). Stderr goes to stderr."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.returncode == 0
    except subprocess.TimeoutExpired:
        return "", False

def main():
    today = datetime.now(timezone.utc)
    date_dir = today.strftime("%Y/%m/%d")
    cache_dir = CACHE_ROOT / date_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Fetch tweets from list (twitterapi.io primary)
    print(f"[fetching tweets from list {LIST_ID}]", file=sys.stderr)
    tweets_raw, ok = run([sys.executable, str(XDIGEST), "list-tweets", LIST_ID,
                           "--max", str(MAX_TWEETS)], timeout=120)
    if not ok:
        print("ERROR: Failed to fetch tweets. Both xapi.py and twitterapi.io unavailable.", file=sys.stderr)
        sys.exit(1)

    # Step 3: Fetch links-only
    links_raw, _ = run([sys.executable, str(XDIGEST), "list-tweets", LIST_ID,
                         "--max", str(MAX_TWEETS), "--links-only"], timeout=120)

    # Step 4: Cache raw data for weekly/monthly LLM jobs
    (cache_dir / "tweets-raw.txt").write_text(tweets_raw)
    (cache_dir / "tweets-links.txt").write_text(links_raw)
    print(f"[cached to {cache_dir}]", file=sys.stderr)

    # Step 5: Output daily digest (stdout = delivery)
    # Count non-RT tweets for the header
    lines = tweets_raw.strip().split("\n")
    tweet_count = sum(1 for l in lines if l.startswith("[@"))
    rt_count = sum(1 for l in lines if l.startswith("[@") and "RT @" in l)

    print(f"X Daily Signal — {today.strftime('%Y-%m-%d')}")
    print(f"{tweet_count} tweets ({rt_count} RTs) from AI High Signal list")
    print()
    print(tweets_raw.strip())

if __name__ == "__main__":
    main()
