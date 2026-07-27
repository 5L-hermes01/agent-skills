#!/usr/bin/env python3
"""
Unified X digest fetcher — transparent dual-backend.

Primary:  xapi.py (X API v2 OAuth2)  →  api.x.com/2/lists/{id}/tweets
Fallback: twitterapi.io              →  api.twitterapi.io/twitter/tweet/advanced_search

Completely transparent to the caller. Same output format regardless
of which backend served the data.

Usage:
    python3 xdigest_fetch.py list-tweets LIST_ID [--max N] [--json] [--links-only] [--enrich]
    python3 xdigest_fetch.py bookmarks [--max N] [--json] [--links-only] [--enrich]
    python3 xdigest_fetch.py search "query" [--max N] [--json] [--links-only]

Flags:
    --enrich    After primary fetch, re-fetch tweet IDs via twitterapi.io
                batch endpoint to get extra fields (viewCount, bookmarkCount,
                conversationId, nested quoted/retweeted tweets).
                Only meaningful for list-tweets and bookmarks.

Output format matches xapi.py exactly for --json and --links-only.
Text mode includes an [enriched] note at the top when enrichment was applied.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
XAPI_SCRIPT = "/opt/data/scripts/xapi.py"
KNOWN_LISTS = {
    "1585430245762441216": "AI High Signal",
    "207282755": "Concentrate",
    "204414139": "High-Level Work Related",
}

TWITTERAPI_KEY = os.environ.get("TWITTERAPI_API_KEY", "")
TWITTERAPI_BASE = "https://api.twitterapi.io/twitter"
TWITTERAPI_RATE_LIMIT = 6  # seconds between calls (free tier: 1 req/5s)

def _require_twitterapi_key():
    """Raise RuntimeError if TWITTERAPI_API_KEY is not set. Called only when twitterapi.io is about to be used."""
    if not TWITTERAPI_KEY:
        raise RuntimeError("TWITTERAPI_API_KEY environment variable is not set")

CACHE_DIR = "/opt/data/cache/xdigest"
LOG_FILE = "/opt/data/logs/digest-runs.jsonl"
os.makedirs(CACHE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# twitterapi.io helpers
# ---------------------------------------------------------------------------

def twitterapi_get(endpoint, params=None, retries=2):
    """GET twitterapi.io endpoint with rate-limit handling."""
    _require_twitterapi_key()
    url = f"{TWITTERAPI_BASE}{endpoint}"
    if params:
        filtered = {k: v for k, v in params.items() if v is not None and v != ""}
        if filtered:
            qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in filtered.items())
            url += "?" + qs

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"X-API-Key": TWITTERAPI_KEY})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 429 and attempt < retries:
                wait = TWITTERAPI_RATE_LIMIT * (attempt + 1)
                print(f"  [twitterapi.io] 429 rate limit, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            return {"_error": f"HTTP {e.code}: {body[:300]}", "_status_code": e.code}
        except Exception as e:
            if attempt < retries:
                time.sleep(TWITTERAPI_RATE_LIMIT)
                continue
            return {"_error": str(e)}
    return {"_error": "Max retries exceeded"}


def twitterapi_batch_tweets(tweet_ids):
    """Batch fetch tweets by IDs via twitterapi.io.
    
    Returns dict mapping tweet_id -> tweet dict with enriched fields.
    """
    if not tweet_ids:
        return {}
    
    chunk_size = 50  # batch up to 50 per call
    result = {}
    
    for i in range(0, len(tweet_ids), chunk_size):
        chunk = tweet_ids[i:i + chunk_size]
        ids_str = ",".join(chunk)
        resp = twitterapi_get("/tweets", {"tweet_ids": ids_str})
        
        if "_error" in resp:
            print(f"  [twitterapi.io] batch enrichment failed: {resp['_error']}", file=sys.stderr)
            # Don't abort — enrichment is best-effort
            break
        
        for t in resp.get("tweets", []):
            tid = str(t.get("id", ""))
            if tid:
                result[tid] = t
        
        # Rate-limit between chunks
        if i + chunk_size < len(tweet_ids):
            time.sleep(TWITTERAPI_RATE_LIMIT)
    
    return result


def twitterapi_search_fallback(query, max_results=50):
    """Fallback: search tweets via twitterapi.io when xapi.py fails.
    
    Returns dict in xapi.py-compatible format (keys: "data", "includes").
    """
    resp = twitterapi_get("/tweet/advanced_search", {
        "query": query,
        "queryType": "Latest",
        "max_results": min(max_results, 100),
    })
    
    if "_error" in resp:
        return {"_error": resp["_error"]}
    
    tweets = resp.get("tweets", [])
    data = []
    users_map = {}
    
    for t in tweets:
        data.append({
            "id": str(t.get("id", "")),
            "text": t.get("text", ""),
            "author_id": str(t.get("author", {}).get("id", "")),
            "created_at": t.get("createdAt", ""),
            "public_metrics": {
                "like_count": t.get("likeCount", 0),
                "retweet_count": t.get("retweetCount", 0),
                "reply_count": t.get("replyCount", 0),
                "quote_count": t.get("quoteCount", 0),
            },
            "_source": "twitterapi.io",
            "_view_count": t.get("viewCount"),
            "_bookmark_count": t.get("bookmarkCount"),
            "_is_reply": t.get("isReply"),
            "_is_quote": t.get("isQuote"),
            "_is_retweet": t.get("isRetweet"),
            "_conversation_id": t.get("conversationId"),
        })
        
        author = t.get("author", {})
        if author.get("id") and author["id"] not in users_map:
            users_map[author["id"]] = {
                "id": author["id"],
                "name": author.get("name", ""),
                "username": author.get("userName", ""),
                "_profile_picture": author.get("profilePicture"),
                "_followers": author.get("followers"),
            }
    
    return {
        "data": data,
        "includes": {"users": list(users_map.values())},
        "meta": {"result_count": len(data), "_source": "twitterapi.io"},
    }


def twitterapi_list_timeline(list_id, max_results=50):
    """Fetch tweets from an X list via twitterapi.io list timeline endpoint.
    
    Direct replacement for xapi.py list-tweets when credits are depleted.
    Uses GET /twitter/list/tweets_timeline?listId=X with pagination.
    
    Returns dict in xapi.py-compatible format (keys: "data", "includes").
    """
    all_tweets = []
    users_map = {}
    cursor = ""
    
    while len(all_tweets) < max_results:
        params = {
            "listId": list_id,
        }
        if cursor:
            params["cursor"] = cursor
        
        resp = twitterapi_get("/list/tweets_timeline", params)
        
        if "_error" in resp:
            if not all_tweets:
                return {"_error": resp["_error"]}
            break  # Return what we have if partial success
        
        tweets = resp.get("tweets", [])
        if not tweets:
            break
        
        for t in tweets:
            all_tweets.append({
                "id": str(t.get("id", "")),
                "text": t.get("text", ""),
                "author_id": str(t.get("author", {}).get("id", "")),
                "created_at": t.get("createdAt", ""),
                "public_metrics": {
                    "like_count": t.get("likeCount", 0),
                    "retweet_count": t.get("retweetCount", 0),
                    "reply_count": t.get("replyCount", 0),
                    "quote_count": t.get("quoteCount", 0),
                },
                "_source": "twitterapi.io",
                "_view_count": t.get("viewCount"),
                "_bookmark_count": t.get("bookmarkCount"),
                "_is_reply": t.get("isReply"),
                "_is_quote": t.get("isQuote"),
                "_is_retweet": t.get("isRetweet"),
                "_conversation_id": t.get("conversationId"),
            })
            
            author = t.get("author", {})
            if author.get("id") and author["id"] not in users_map:
                users_map[author["id"]] = {
                    "id": author["id"],
                    "name": author.get("name", ""),
                    "username": author.get("userName", ""),
                    "_profile_picture": author.get("profilePicture"),
                    "_followers": author.get("followers"),
                }
        
        if not resp.get("has_next_page"):
            break
        cursor = resp.get("next_cursor", "")
        
        # Respect rate limits
        if cursor:
            import time
            time.sleep(1.05)
    
    return {
        "data": all_tweets[:max_results],
        "includes": {"users": list(users_map.values())},
        "meta": {"result_count": min(len(all_tweets), max_results), "_source": "twitterapi.io"},
    }


# ---------------------------------------------------------------------------
# xapi.py wrapper
# ---------------------------------------------------------------------------

def run_xapi(args, timeout=120):
    """Run xapi.py and return (exit_code, stdout, stderr)."""
    cmd = [sys.executable, XAPI_SCRIPT] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except FileNotFoundError:
        return -2, "", f"xapi.py not found at {XAPI_SCRIPT}"
    except Exception as e:
        return -3, "", str(e)


# ---------------------------------------------------------------------------
# Enrichment: overlay twitterapi.io fields onto xapi.py data
# ---------------------------------------------------------------------------

def enrich_tweet_data(xapi_json_path, tweet_ids):
    """Fetch enriched fields from twitterapi.io and overlay onto JSON data file."""
    enriched = twitterapi_batch_tweets(tweet_ids)
    if not enriched:
        return 0
    
    # Read the xapi.py JSON output
    with open(xapi_json_path) as f:
        data = json.load(f)
    
    enriched_count = 0
    for t in data.get("data", []):
        tid = t.get("id", "")
        et = enriched.get(tid)
        if et:
            t["_view_count"] = et.get("viewCount")
            t["_bookmark_count"] = et.get("bookmarkCount")
            t["_conversation_id"] = et.get("conversationId")
            t["_is_reply"] = et.get("isReply")
            t["_is_quote"] = et.get("isQuote")
            t["_is_retweet"] = et.get("isRetweet")
            t["_source"] = "xapi.py+twitterapi.io"
            enriched_count += 1
    
    data["_enriched"] = enriched_count
    data["_enriched_at"] = datetime.now(timezone.utc).isoformat()
    
    with open(xapi_json_path, "w") as f:
        json.dump(data, f, indent=2)
    
    msg = f"  [enrich] Overlaid twitterapi.io fields on {enriched_count}/{len(data.get('data', []))} tweets"
    print(msg, file=sys.stderr)
    return enriched_count


def extract_tweet_ids(text):
    """Extract tweet IDs from xapi.py output (handles both JSON and text modes)."""
    import re
    ids = []
    # Try JSON mode first: find "id": "12345" patterns
    for match in re.finditer(r'"id"\s*:\s*"(\d+)"', text):
        tid = match.group(1)
        if tid not in ids:
            ids.append(tid)
    # Fallback: text mode with URL patterns
    if not ids:
        for match in re.finditer(r'https://x\.com/i/status/(\d+)', text):
            tid = match.group(1)
            if tid not in ids:
                ids.append(tid)
    return ids


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_run(entry):
    """Append JSONL entry to digest log."""
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def extract_tweet_ids_from_urls(urls):
    """Extract tweet IDs from a list of X/Twitter URLs.
    Returns (tweet_ids, profile_urls, skipped) where:
      tweet_ids: list of numeric tweet IDs
      profile_urls: list of profile URLs (x.com/username without /status/)
      skipped: list of non-tweet URLs (home, notifications, console, etc.)
    """
    import re
    tweet_ids = []
    profile_urls = []
    skipped = []
    
    for url in urls:
        url = url.strip().rstrip("/")
        # Match tweet status URLs: x.com/.../status/XXXXX
        m = re.search(r'(?:x|twitter)\.com/\S+/status/(\d+)', url)
        if m:
            tid = m.group(1)
            if tid not in tweet_ids:
                tweet_ids.append(tid)
            continue
        
        # Match photo URLs: x.com/.../status/XXXXX/photo/N
        m = re.search(r'(?:x|twitter)\.com/\S+/status/(\d+)/photo', url)
        if m:
            tid = m.group(1)
            if tid not in tweet_ids:
                tweet_ids.append(tid)
            continue
        
        # Profile URLs: x.com/username (no /status/)
        m = re.match(r'https?://(?:x|twitter)\.com/([a-zA-Z0-9_]+)(?:$|/\s*$)', url)
        if m:
            handle = m.group(1)
            # Skip known non-profile paths
            if handle.lower() in ('home', 'notifications', 'explore', 'settings', 'console', 'i', 'login', 'oauth'):
                skipped.append(url)
            else:
                if url not in profile_urls:
                    profile_urls.append(url)
            continue
        
        skipped.append(url)
    
    return tweet_ids, profile_urls, skipped


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    args = sys.argv[2:]
    
    # Parse flags
    max_results = 50
    json_output = False
    links_only = False
    enrich = False
    clean_args = []
    i = 0
    while i < len(args):
        if args[i] == "--max" and i + 1 < len(args):
            max_results = int(args[i + 1])
            i += 2
        elif args[i] == "--json":
            json_output = True
            i += 1
        elif args[i] == "--links-only":
            links_only = True
            i += 1
        elif args[i] == "--enrich":
            enrich = True
            i += 1
        else:
            clean_args.append(args[i])
            i += 1
    
    # -----------------------------------------------------------------------
    # Command routing
    # -----------------------------------------------------------------------
    
    if cmd == "tweets":
        """Fetch individual tweets by URL or tweet ID via twitterapi.io.
        
        Usage:
            python3 xdigest_fetch.py tweets URL1 URL2 ... [--json] [--links-only]
        
        Twitterapi.io is cheaper than xapi.py for individual tweet lookups
        ($0.15/1k tweets vs $0.005/call for xapi.py). Pure twitterapi.io path.
        """
        if not clean_args:
            print("Usage: tweets URL [URL...] [--json] [--links-only]", file=sys.stderr)
            sys.exit(1)
        
        tweet_ids, profile_urls, skipped = extract_tweet_ids_from_urls(clean_args)
        
        if not tweet_ids:
            print("FATAL: No tweet IDs found in the provided URLs", file=sys.stderr)
            if profile_urls:
                print(f"  Found {len(profile_urls)} profile URLs (no/status/ path):", file=sys.stderr)
                for pu in profile_urls:
                    print(f"    {pu}", file=sys.stderr)
            sys.exit(1)
        
        # Log what we found
        print(f"  [tweets] {len(tweet_ids)} tweet IDs, {len(profile_urls)} profile URLs, {len(skipped)} skipped", file=sys.stderr)
        if skipped:
            print(f"  [tweets] Skipped (non-tweet URLs): {skipped}", file=sys.stderr)
        
        # Fetch via twitterapi.io batch endpoint
        enriched = twitterapi_batch_tweets(tweet_ids)
        
        if not enriched:
            print("FATAL: twitterapi.io returned no data for any tweet ID", file=sys.stderr)
            sys.exit(1)
        
        # Build output in xapi.py-compatible format
        data = []
        users_map = {}
        for tid, et in enriched.items():
            author = et.get("author", {})
            author_id = str(author.get("id", "")) if isinstance(author, dict) else ""
            author_username = author.get("userName", "") if isinstance(author, dict) else ""
            author_name = author.get("name", "") if isinstance(author, dict) else ""
            
            data.append({
                "id": tid,
                "text": et.get("text", ""),
                "author_id": author_id,
                "created_at": et.get("createdAt", ""),
                "public_metrics": {
                    "like_count": et.get("likeCount", 0),
                    "retweet_count": et.get("retweetCount", 0),
                    "reply_count": et.get("replyCount", 0),
                    "quote_count": et.get("quoteCount", 0),
                },
                "_source": "twitterapi.io",
                "_view_count": et.get("viewCount"),
                "_bookmark_count": et.get("bookmarkCount"),
                "_is_reply": et.get("isReply"),
                "_is_quote": et.get("isQuote"),
                "_is_retweet": et.get("isRetweet"),
                "_conversation_id": et.get("conversationId"),
                "_extended_entities": et.get("extendedEntities", {}),
            })
            if author_id and author_id not in users_map:
                users_map[author_id] = {
                    "id": author_id,
                    "name": author_name,
                    "username": author_username,
                }
        
        # Add profile-only entries for profile_urls that couldn't be fetched
        profile_note = ""
        if profile_urls:
            profile_note = f"\n[Profile URLs (no tweet data): {' '.join(profile_urls)}]"
        
        if json_output:
            result = {
                "data": data,
                "includes": {"users": list(users_map.values())} if users_map else {},
                "meta": {"result_count": len(data), "_source": "twitterapi.io"},
                "_profile_urls": profile_urls if profile_urls else [],
            }
            print(json.dumps(result, indent=2))
        elif links_only:
            for t in data:
                handle = users_map.get(t.get("author_id", ""), {}).get("username", "?")
                print(f"@{handle}: https://x.com/i/status/{t['id']}")
            if profile_urls:
                for pu in profile_urls:
                    print(f"# profile: {pu}")
        else:
            print(f"[Fetched via twitterapi.io — individual tweet lookup]")
            print(f"[{len(data)} tweets, {len(profile_urls)} profiles]\n")
            for t in data:
                author = users_map.get(t.get("author_id", ""), {})
                handle = f"@{author.get('username', t['author_id'])} ({author.get('name', '')})" if author else f"uid:{t['author_id']}"
                text = t.get("text", "")
                metrics = t.get("public_metrics", {})
                created = t.get("created_at", "")
                tid = t.get("id", "")
                print(f"[{handle}] {text}")
                print(f"  ♥{metrics.get('like_count',0)} 🔁{metrics.get('retweet_count',0)} 💬{metrics.get('reply_count',0)}")
                print(f"  {created} | https://x.com/i/status/{tid}")
                
                # Extract and print media URLs if present
                media_urls = []
                ext_entities = t.get("_extended_entities", {})
                if ext_entities and "media" in ext_entities:
                    for m in ext_entities["media"]:
                        if m.get("type") == "photo" and "media_url_https" in m:
                            media_urls.append(m["media_url_https"])
                if media_urls:
                    print(f"  📷 Media: " + " | ".join(media_urls))
                    
                print("-" * 60)
            if profile_urls:
                print(f"\n[Unfetchable profiles (no tweet data)]")
                for pu in profile_urls:
                    print(f"  {pu}")
        
        log_run({
            "command": cmd,
            "tweet_ids": len(tweet_ids),
            "fetched": len(data),
            "profiles": len(profile_urls),
            "source": "twitterapi.io",
            "status": "ok",
        })
        sys.exit(0)
    
    elif cmd == "list-tweets":
        list_id = clean_args[0] if clean_args else "1585430245762441216"
        list_name = KNOWN_LISTS.get(list_id, "unknown")
        source = "twitterapi.io"

        # Step 1: Try twitterapi.io (primary — no OAuth dependency)
        print(f"  [primary] fetching list timeline from twitterapi.io for list {list_id}...", file=sys.stderr)
        primary_resp = twitterapi_list_timeline(list_id, max_results)

        if "_error" not in primary_resp:
            # twitterapi.io succeeded
            tweets = primary_resp.get("data", [])
            users = primary_resp.get("includes", {}).get("users", [])
            users_map = {u["id"]: u for u in users}

            if json_output:
                print(json.dumps(primary_resp, indent=2))
            elif links_only:
                for t in tweets:
                    tid = t["id"]
                    handle = users_map.get(t.get("author_id", ""), {}).get("username", "?")
                    print(f"@{handle}: https://x.com/i/status/{tid}")
            else:
                print(f"[Fetched via twitterapi.io]\n")
                for t in tweets:
                    uid = t.get("author_id", "")
                    author = users_map.get(uid, {})
                    handle = f"@{author.get('username', uid)} ({author.get('name', '')})" if author else f"uid:{uid}"
                    text = t.get("text", "")
                    metrics = t.get("public_metrics", {})
                    created = t.get("created_at", "")
                    tid = t.get("id", "")
                    print(f"[{handle}] {text}")
                    print(f"  ♥{metrics.get('like_count',0)} 🔁{metrics.get('retweet_count',0)} 💬{metrics.get('reply_count',0)}")
                    print(f"  {created} | https://x.com/i/status/{tid}")
                    print("-" * 60)

            log_run({
                "command": cmd,
                "list_id": list_id,
                "source": "twitterapi.io",
                "status": "ok",
            })
            sys.exit(0)

        # Step 2: twitterapi.io failed — try xapi.py fallback
        tw_error = primary_resp.get("_error", "unknown")
        print(f"  [fallback] twitterapi.io failed ({tw_error}), trying xapi.py...", file=sys.stderr)

        xapi_args = ["list-tweets", list_id, "--max", str(max_results)]
        if json_output:
            xapi_args.append("--json")
        if links_only:
            xapi_args.append("--links-only")

        rc, stdout, stderr = run_xapi(xapi_args)

        if rc == 0 and stdout.strip():
            # xapi.py succeeded as fallback
            tweet_ids = extract_tweet_ids(stdout)

            if enrich and not links_only and json_output and tweet_ids:
                tmp_json = os.path.join(CACHE_DIR, f"enrich_{list_id}.json")
                with open(tmp_json, "w") as f:
                    f.write(stdout)
                enriched = enrich_tweet_data(tmp_json, tweet_ids[:100])
                if enriched:
                    with open(tmp_json) as f:
                        print(f.read(), end="")
                    os.remove(tmp_json)
                else:
                    print(stdout, end="")
            else:
                print(stdout, end="")

            log_run({
                "command": cmd,
                "list_id": list_id,
                "source": "xapi.py",
                "enriched": enrich,
                "status": "fallback_ok",
            })
            sys.exit(0)

        # Both failed
        xapi_error = stderr.strip() or f"exit code {rc}"
        print(f"FATAL: Both twitterapi.io and xapi.py failed", file=sys.stderr)
        print(f"  twitterapi: {tw_error}", file=sys.stderr)
        print(f"  xapi.py:    {xapi_error}", file=sys.stderr)
        log_run({
            "command": cmd,
            "list_id": list_id,
            "source": "both_failed",
            "status": "error",
            "error": f"twitterapi: {tw_error}; xapi: {xapi_error}",
        })
        sys.exit(1)
    
    elif cmd == "bookmarks":
        xapi_args = ["bookmarks", "--max", str(max_results)]
        if json_output:
            xapi_args.append("--json")
        if links_only:
            xapi_args.append("--links-only")
        
        rc, stdout, stderr = run_xapi(xapi_args)
        
        if rc == 0 and stdout.strip():
            print(stdout, end="")
            log_run({"command": cmd, "source": "xapi.py", "status": "ok"})
            sys.exit(0)
        
        print(f"  [fallback] xapi.py bookmarks failed ({stderr.strip()}), cannot fall back (twitterapi.io bookmarks needs login_cookie)", file=sys.stderr)
        print(f"FATAL: xapi.py bookmarks failed. twitterapi.io bookmarks requires login_cookie, not supported yet.", file=sys.stderr)
        log_run({"command": cmd, "source": "both_failed", "status": "error", "error": stderr.strip()})
        sys.exit(1)
    
    elif cmd == "search":
        query = " ".join(clean_args)
        xapi_args = ["search", query, "--max", str(max_results)]
        if json_output:
            xapi_args.append("--json")
        if links_only:
            xapi_args.append("--links-only")
        
        rc, stdout, stderr = run_xapi(xapi_args)
        
        if rc == 0 and stdout.strip():
            print(stdout, end="")
            log_run({"command": cmd, "source": "xapi.py", "status": "ok"})
            sys.exit(0)
        
        # Fallback to twitterapi.io advanced search
        print(f"  [fallback] xapi.py search failed ({stderr.strip()}), trying twitterapi.io...", file=sys.stderr)
        fallback_resp = twitterapi_search_fallback(query, max_results)
        
        if "_error" in fallback_resp:
            print(f"FATAL: Both xapi.py and twitterapi.io search failed", file=sys.stderr)
            print(f"  xapi.py:    {stderr.strip()}", file=sys.stderr)
            print(f"  twitterapi: {fallback_resp['_error']}", file=sys.stderr)
            log_run({"command": cmd, "source": "both_failed", "status": "error"})
            sys.exit(1)
        
        tweets = fallback_resp.get("data", [])
        users = fallback_resp.get("includes", {}).get("users", [])
        users_map = {u["id"]: u for u in users}
        
        if json_output:
            print(json.dumps(fallback_resp, indent=2))
        elif links_only:
            for t in tweets:
                tid = t["id"]
                handle = users_map.get(t.get("author_id", ""), {}).get("username", "?")
                print(f"@{handle}: https://x.com/i/status/{tid}")
        else:
            print(f"[Fetched via twitterapi.io — xapi.py was unavailable]\n")
            for t in tweets:
                uid = t.get("author_id", "")
                author = users_map.get(uid, {})
                handle = f"@{author.get('username', uid)} ({author.get('name', '')})" if author else f"uid:{uid}"
                text = t.get("text", "")
                metrics = t.get("public_metrics", {})
                created = t.get("created_at", "")
                tid = t.get("id", "")
                print(f"[{handle}] {text}")
                print(f"  ♥{metrics.get('like_count',0)} 🔁{metrics.get('retweet_count',0)} 💬{metrics.get('reply_count',0)}")
                print(f"  {created} | https://x.com/i/status/{tid}")
                print("-" * 60)
        
        log_run({"command": cmd, "source": "twitterapi.io", "status": "fallback_ok"})
        sys.exit(0)
    
    elif cmd == "digest-validate":
        # Pass through to xapi.py's validator
        rc, stdout, stderr = run_xapi(["digest-validate"] + clean_args)
        print(stdout, end="")
        sys.exit(rc)
    
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()