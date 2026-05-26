---
name: x-digest
description: Fetch and summarize X/Twitter list feeds into a digest format. Uses xapi.py (X API v2 OAuth2) as primary with transparent twitterapi.io fallback and enrichment.
version: 4.1.0
author: Hermes Agent 01
metadata:
  hermes:
    tags: [twitter, x, social-media, digest]
---

# x-digest — X/Twitter List Digest

Fetches tweets from X lists and formats them as a readable digest. Uses **two backends transparently**:
- **Primary**: xapi.py (X API v2 OAuth2) — direct `api.x.com/2/...` calls
- **Fallback/enrichment**: twitterapi.io (third-party proxy) — `api.twitterapi.io/twitter/...` with X-API-Key (env var `TWITTERAPI_API_KEY`)

The unified fetcher `/opt/data/scripts/xdigest_fetch.py` wraps both backends. You call it the same way regardless of which backend served the data.

## Prerequisites

- Working OAuth2 token in `/opt/data/config/x-oauth2-tokens.json` (for xapi.py primary)
- `TWITTERAPI_API_KEY` env var with a valid X-API-Key header value (for twitterapi.io fallback, enrichment, and individual tweet lookup)
- Python 3 (stdlib only, no pip deps)

## Unified Fetcher

`/opt/data/scripts/xdigest_fetch.py` wraps both backends:

| Command | Description |
|---------|-------------|
| `list-tweets LIST_ID [--max N] [--json] [--links-only] [--enrich]` | Tweets from an X list (xapi.py primary, twitterapi.io fallback) |
| `tweets URL [URL...] [--json] [--links-only]` | Fetch individual tweets by URL(s) via twitterapi.io batch endpoint (cheaper than xapi.py for one-off lookups). Extracts tweet IDs from URLs automatically. |
| `search "query" [--max N] [--json] [--links-only]` | Search tweets (xapi.py primary, twitterapi.io fallback) |
| `bookmarks [--max N] [--json] [--links-only] [--enrich]` | User bookmarks (xapi.py only) |
| `digest-validate FILE` | Validate URLs in a digest file |

The script is transparent: same args, same output format regardless of backend.
Add `--enrich` to overlay twitterapi.io fields onto JSON output (viewCount, bookmarkCount, conversationId, isReply/isQuote/isRetweet).

## User Preferences (do not violate these in future sessions)

- **"Set and forget" transparency**: New integrations must be wired transparently into the unified fetcher. Do not propose parallel scripts or manual switching logic.
- **Evidence over assertion when correcting**: If the user challenges an understanding, provide a runnable code or log trace showing exactly what happens, not a prose explanation. "Give me a detailed sequence of events" means log-level tracing, not bullet-point summaries.
- **Face tension, cost-sensitive, but techical**: the user wants to understand the call graphs (endpoint, auth, cost, whether LLM inference is involved), not just a call count. Be precise and avoid mislabeling calls' destinations — x_search calls `api.x.ai/v1/responses`, not `api.x.com`; list-tweets calls `api.x.com/2/...`; twitterapi.io calls `api.twitterapi.io/twitter/...`. When you're wrong, say so explicitly, then fix it.
- **Author attribution**: Always use "Hermes Agent 01" as the author in skill metadata to avoid confusion with other instances.

## Quick Start

```bash
# Fetch latest from AI High Signal list (unified — auto-fallback if xapi.py fails)
python3 /opt/data/scripts/xdigest_fetch.py list-tweets 1585430245762441216 --max 50

# With twitterapi.io enrichment for extra fields (viewCount, conversationId, etc.)
python3 /opt/data/scripts/xdigest_fetch.py list-tweets 1585430245762441216 --max 50 --json --enrich

# Links-only output (for appending to digests — NEVER let the LLM touch this)
python3 /opt/data/scripts/xdigest_fetch.py list-tweets 1585430245762441216 --max 50 --links-only

# Search with fallback
python3 /opt/data/scripts/xdigest_fetch.py search "AI agents" --max 20

# Fetch individual tweets by URL (twitterapi.io — cheaper for one-off lookups)
python3 /opt/data/scripts/xdigest_fetch.py tweets https://x.com/username/status/12345 https://x.com/other/status/67890

# Fetch individual tweets as JSON (with enriched fields from twitterapi.io)
python3 /opt/data/scripts/xdigest_fetch.py tweets https://x.com/username/status/12345 --json

# Links-only for individual tweets
python3 /opt/data/scripts/xdigest_fetch.py tweets https://x.com/username/status/12345 --links-only
```

## Known Lists

| Name | List ID | Recommended Max |
|------|---------|-----------------|
| AI High Signal | 1585430245762441216 | 50 (100 with --all) |
| Concentrate | 207282755 | 50 (100 with --all) |
| High-Level Work Related | 204414139 | 50 (100 with --all) |

**Note:** For comprehensive digests, use `--max 100`. If timeout issues occur (common in headless environments), reduce to `--max 50-60`.

## Cost Analysis & API Architecture

Three ways to get X data. Know which endpoint each calls and what it costs.

| Option | What it calls | Auth | Cost / 50 tweets | LLM involved? |
|--------|--------------|------|-----------------|---------------|
| **xapi.py** (preferred for list digests) | `api.x.com/2/...` — direct X API v2 | OAuth2 bearer token | ~$0.005 (or free within $100/mo Basic tier quota) | No — pure data retrieval |
| **x_search** (xAI tool) | `api.x.ai/v1/responses` — xAI model inference | XAI_API_KEY or SuperGrok OAuth | ~$0.10+/call (grok-4.20-reasoning inference) | Yes — returns prose+URLs, not raw tweets |
| **twitterapi.io** (third-party proxy) | `api.twitterapi.io/twitter/...` | X-API-Key header | ~$0.0075 ($0.15/1k tweets, $0.00015 minimum) | No |

### Key distinctions

- **xapi.py** makes direct HTTP GETs to X's servers. One GET per page (max 100 tweets). No model inference. Cacheable (30 min TTL for list-tweets).
- **x_search** sends a POST to xAI's inference API with the `grok-4.20-reasoning` model and `{type: "x_search"}` tool. xAI's backend fetches the tweets internally. We pay for model tokens.
- **twitterapi.io** is a third-party proxy. No OAuth, X-API-Key only. **Has no list-tweets endpoint** (returns 404). Bookmarks needs a `login_cookie`. Rich extra fields: viewCount, bookmarkCount, conversationId, nested quoted/retweeted tweets.

### Which to use for what

- **Digest (list-tweets)**: xapi.py primary, twitterapi.io fallback. Use xdigest_fetch.py and it's handled.
- **Individual tweet lookup (one-off URLs)**: twitterapi.io via `xdigest_fetch.py tweets` command. Cheaper than xapi.py for single tweets because twitterapi.io has a dedicated batch `/tweets` endpoint with $0.15/1k pricing.
- **Search with prose analysis**: x_search. Get summarized content with context.

## Digest Workflow (hardened + transparent fallback)

### Step 0: Pre-flight — refresh token

Always refresh the OAuth2 token before fetching tweets. Token expires every 2 hours.

If refresh fails, xdigest_fetch.py will automatically fall back to twitterapi.io. This is transparent — no manual intervention needed.

```bash
python3 /opt/data/scripts/xapi.py refresh-token
```

Cache is handled by xapi.py on disk at `/opt/data/cache/xapi/`. TTL: 30 min for list-tweets/bookmarks, 30 days for search/user/timeline.

### Step 1: Fetch tweets (full + links-only)

Use xdigest_fetch.py for transparent dual-backend support:

```bash
# Full output for the LLM to read (auto-fallback to twitterapi.io if xapi.py fails)
python3 /opt/data/scripts/xdigest_fetch.py list-tweets 1585430245762441216 --max 50 > /tmp/digest_tweets.txt

# Links-only output — NEVER let the LLM touch this
python3 /opt/data/scripts/xdigest_fetch.py list-tweets 1585430245762441216 --max 50 --links-only > /tmp/digest_links.txt
```

For individual tweet URLs (not a list):
```bash
python3 /opt/data/scripts/xdigest_fetch.py tweets URL1 URL2 ... > /tmp/digest_tweets.txt
python3 /opt/data/scripts/xdigest_fetch.py tweets URL1 URL2 ... --links-only > /tmp/digest_links.txt
```

If twitterapi.io also fails, note the error in the log and skip posting.

### Step 2: Write thematic summary

- Read ALL tweet content from `/tmp/digest_tweets.txt` — skip pure RTs unless they amplify something notable
- Group by THEME using the **unified cross-platform theme system** (canonical source: load the `unified-digest-themes` skill).
- Write a short paragraph per theme summarizing what's discussed and why it matters. Mention author handles.
- If a story could fit multiple themes, use the **primary signal** rule: identify the central new information and place it under the most specific matching theme.

### Step 3: Append programmatic links section

**CRITICAL: The Links section must be generated by Python, NOT by the LLM.**

After writing the prose, append the contents of `/tmp/digest_links.txt` verbatim as the Links section. Do NOT rewrite, reorder, or reformat these URLs. The `--links-only` output is authoritative and guaranteed correct.

### Step 4: Validate before posting

```bash
# Write your full digest to a temp file, then validate
python3 /opt/data/scripts/xdigest_fetch.py digest-validate /tmp/digest_output.txt
```

If validation fails (exit code 1), fix the broken URLs before posting. If validation passes, post the digest.

### Step 5: Log the run

Append a JSONL entry to `/opt/data/logs/digest-runs.jsonl`:

```json
{"ts": "ISO_TIMESTAMP", "status": "ok|broken|error|fallback_ok", "urls_total": N, "urls_valid": N, "urls_broken": N, "note": "brief description including which backend served the data"}
```

This enables success rate tracking over time.

### Format Preference (important)

User prefers PLAIN TEXT digests:
- No markdown headers (#)
- No emoji section dividers (━━━━)
- No bold (**)
- Simple date header, blank lines between sections
- Conversational tone, not press-release
- Raw links section at the end for clicking through

## Cron Jobs

The `ai-high-signal-digest` cron job runs daily at 09:00 UTC, delivering thematic summaries to `discord:#x-tweet-digests`.

Format preference: plain conversational summaries grouped by theme, with raw tweet links at the end. No fancy markdown, no emoji section dividers.

## Pitfalls

- Token expires every 2 hours — refresh before every run (Step 0)
- List endpoint max is 100 tweets per request, pagination via `pagination_token`
- Retweets show original author_id but the text includes `"RT @user:"` prefix
- **twitterapi.io free tier**: 1 request per 5 seconds. `xdigest_fetch.py` handles 429s with backoff and retry.
- NEVER let the LLM construct or rewrite tweet URLs — always use `--links-only` output verbatim
- The `--enrich` flag works only with `--json` output. It adds `_view_count`, `_bookmark_count`, `_conversation_id`, `_is_reply`, `_is_quote`, `_is_retweet` fields.
- twitterapi.io has no list-tweets endpoint — when xapi.py fails, the fallback uses topic-based advanced search instead. This returns different (broader) results, not the exact list membership.
- Bookmarks have no twitterapi.io fallback — requires login_cookie.
- For digest validation failures, check the broken URLs manually — common causes are expired tweet IDs, suspended accounts, or rate-limit blocks.
- **The `tweets` command in xdigest_fetch.py is wired into `main()` at line 359.** Routes URL arguments through `extract_tweet_ids_from_urls()` to `twitterapi_batch_tweets()`. Output matches other commands (text/json/links-only). Profile URLs and noise (console.x.com, /home) are filtered and reported separately. See `references/tweets-command.md` for the implementation reference.

## Transparent Fallback Flow

When xdigest_fetch.py runs list-tweets:

1. Try `GET https://api.x.com/2/lists/{id}/tweets` via xapi.py (OAuth2)
2. If that fails (401/403/network): try `GET https://api.twitterapi.io/twitter/tweet/advanced_search` with a topic query mapping from `LIST_TOPICS`
3. If both fail: print error, exit 1

When `--enrich` is used with JSON:
1. Fetch via xapi.py as normal
2. Extract tweet IDs from the result
3. Batch-fetch via `GET https://api.twitterapi.io/twitter/tweets?tweet_ids=...`
4. Overlay extra fields onto the xapi.py output

When `tweets` command runs:
1. Parse all URL arguments, extract tweet IDs from `/status/XXXXX` patterns
2. Filter out non-tweet URLs (profiles, console.x.com, home, notifications)
3. Call `twitterapi_batch_tweets(tweet_ids)` — batch-fetches via twitterapi.io `/tweets` endpoint (chunks of 50)
4. Format output identically to other commands (text/json/links-only)
5. No xapi.py fallback — twitterapi.io is the primary (and cheaper) backend for this path

This is completely transparent to the caller. The output format is identical.

## Support Files

| File | Purpose |
|------|---------|
| `references/api-endpoint-mapping.md` | Full HTTP trace for xapi.py and twitterapi.io with line numbers |
| `references/api-validation.md` | Cross-source content matching — how to validate a new data source against cached data |
| `references/fallback-topic-mapping.md` | `LIST_TOPICS` dict for twitterapi.io topic-search fallback when xapi.py is down |
| `references/tweets-command.md` | Implementation reference for the `tweets` CLI command — URL parsing, batch fetch, output formatting |
| `scripts/xdigest_fetch.py` | Unified fetcher script — primary xapi.py + twitterapi.io fallback/enrichment. Keep this alongside xapi.py in `/opt/data/scripts/` and update it when adding new backends or list IDs. |