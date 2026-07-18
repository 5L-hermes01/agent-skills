#!/usr/bin/env python3
"""
Daily X-digest delivery to Signal — individual tweets per message.

Pipeline:
1. Fetch 50 tweets from AI High Signal list via xdigest_fetch.py
2. Sort by engagement signal score
3. Pick top ~15 high-signal items
4. Send each as individual `hermes send` message (4s delay between)
5. Log to digest-runs.jsonl

Usage:
    python3 /opt/data/skills/social-media/x-digest/scripts/daily_signal_delivery.py

Designed to run as a no_agent=True cron job. Produces no stdout on success
(runs silently, as expected for no_agent=True). On failure, prints error
message that cron delivers as an alert.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

# Config
LIST_ID = "1585430245762441216"  # AI High Signal
MAX_TWEETS = 50
MAX_TO_SEND = 15  # Don't spam — send the best ones
SIGNAL_TARGET = "signal:Twitter Processing"
SIGNAL_DELAY = 4  # seconds between Signal sends (rate limit)
LOG_FILE = "/opt/data/logs/digest-runs.jsonl"

# Engagement score weights
LIKE_WEIGHT = 1
RETWEET_WEIGHT = 3
REPLY_WEIGHT = 2


def log_run(entry):
    """Append a JSONL entry to the digest log."""
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Log write failed: {e}", file=sys.stderr)


def send_signal(message):
    """Send a single message to Signal via hermes send."""
    result = subprocess.run(
        ["hermes", "send", "--to", SIGNAL_TARGET, message],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"Signal send failed: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def engagement_score(tweet):
    """Calculate engagement signal score for a tweet."""
    metrics = tweet.get("public_metrics", {})
    likes = metrics.get("like_count", 0)
    retweets = metrics.get("retweet_count", 0)
    replies = metrics.get("reply_count", 0)
    return likes * LIKE_WEIGHT + retweets * RETWEET_WEIGHT + replies * REPLY_WEIGHT


def is_rt(tweet):
    """Check if tweet is a pure retweet (starts with RT @)."""
    text = tweet.get("text", "")
    return text.startswith("RT @") or text.startswith("RT @@")


def format_tweet_message(tweet, users_map):
    """Format a tweet as a short Signal message: @handle — excerpt + link."""
    uid = tweet.get("author_id", "")
    user = users_map.get(uid, {})
    handle = user.get("username", uid)
    
    text = tweet.get("text", "")
    # Strip RT prefix for cleaner display
    if text.startswith("RT @"):
        text = text[text.index(":", 3)+1:].strip() if ":" in text[3:] else text
    
    # Clean up the text: strip URLs at the end (the link goes separately)
    words = text.split()
    clean_words = [w for w in words if not w.startswith(("http://", "https://", "t.co/"))]
    cleaned = " ".join(clean_words).strip()
    
    # Truncate to reasonable length
    if len(cleaned) > 120:
        cleaned = cleaned[:117] + "…"
    
    tid = tweet.get("id", "")
    url = f"https://x.com/i/status/{tid}"
    
    return f"@{handle}\n{cleaned}\n{url}"


def main():
    xdigest_script = "/opt/data/scripts/xdigest_fetch.py"
    
    # Step 1: Fetch tweets as JSON
    result = subprocess.run(
        ["python3", xdigest_script, "list-tweets", LIST_ID, "--max", str(MAX_TWEETS), "--json"],
        capture_output=True, text=True, timeout=60
    )
    
    if result.returncode != 0 or not result.stdout.strip():
        error_msg = f"Fetch failed (exit {result.returncode}): {result.stderr.strip()[:200]}"
        print(error_msg, file=sys.stderr)
        log_run({"status": "error", "note": error_msg, "urls_total": 0, "urls_valid": 0, "urls_broken": 0})
        sys.exit(1)
    
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        error_msg = f"JSON parse failed: {e}"
        print(error_msg, file=sys.stderr)
        log_run({"status": "error", "note": error_msg, "urls_total": 0, "urls_valid": 0, "urls_broken": 0})
        sys.exit(1)
    
    tweets = data.get("data", [])
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    
    if not tweets:
        print("No tweets returned", file=sys.stderr)
        log_run({"status": "empty", "note": "No tweets in API response"})
        sys.exit(1)
    
    # Step 2: Sort by engagement, filter RIs
    scored = [(engagement_score(t), t) for t in tweets]
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Pick top items: prefer non-RTs, but include high-engagement RTs
    selected = []
    for score, tweet in scored[:MAX_TO_SEND * 2]:  # look at top 30
        if len(selected) >= MAX_TO_SEND:
            break
        if is_rt(tweet) and score < 100:  # skip low-value pure RTs
            continue
        selected.append(tweet)
    
    # Step 3: Send each tweet individually to Signal
    sent_count = 0
    fail_count = 0
    
    for tweet in selected:
        message = format_tweet_message(tweet, users)
        if send_signal(message):
            sent_count += 1
        else:
            fail_count += 1
        time.sleep(SIGNAL_DELAY)
    
    # Step 4: Log
    status = "signal_daily_ok" if fail_count == 0 else f"signal_daily_partial_{fail_count}_failed"
    log_run({
        "status": status,
        "urls_total": len(tweets),
        "urls_valid": sent_count,
        "urls_broken": fail_count,
        "note": f"Fetched {len(tweets)}, selected {len(selected)}, sent {sent_count} to Signal"
    })
    
    # Silent exit on success — no_agent=True delivers nothing
    if fail_count > 0:
        print(f"WARNING: {fail_count}/{len(selected)} Signal sends failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
