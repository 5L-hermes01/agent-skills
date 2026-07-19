---
name: x-digest
description: Fetch and summarize X/Twitter list feeds into a digest format. Uses xapi.py (X API v2 OAuth2) as primary with transparent twitterapi.io fallback and enrichment.
version: 4.4.0
author: Hermes Agent 01
metadata:
  hermes:
    tags: [twitter, x, social-media, digest]
    related_skills: [unified-digest-themes, jargon]
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
- Decode jargon using the `jargon` skill. Scan tweet text for known terms. Skip saturated terms (e.g., LLM, AI). For non-saturated terms, show the kindergarten-level definition. Deduplicate jargon within the digest (explain each term only once).
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

## Delivery to Signal (Daily)

### Format: individual tweets per message

Signal truncates long messages. **Do not batch tweets** into a single prose section with links appendix.
Instead, send each high-signal tweet as its own message using `hermes send`.

### Mechanism: `hermes send`

```bash
hermes send --to "signal:Twitter Processing" "@handle — one-line context\nLink: https://x.com/i/status/ID"
```

`hermes send` reuses the gateway's Signal credentials — no auth needed. It sends text as a native Signal message.

### Signal delivery script

`scripts/daily_signal_delivery.py` does the full pipeline:
1. Fetch 50 tweets via xdigest_fetch.py
2. Sort by engagement (likes + retweets*3 + replies*2)
3. Pick top ~15 high-signal items (skip pure RTs unless they amplify something notable)
4. Send each as an individual `hermes send` message with 4-second delay between sends
5. Log results to `/opt/data/logs/digest-runs.jsonl` with status `signal_daily_ok`

### Format rules (per tweet message)

- Keep each message under 400 chars (tweet text excerpt + link)
- One line of context (user's actual text, not a summary) plus the link
- Use `@handle` prefix consistently
- Link format: `https://x.com/i/status/ID` (raw, no URL shorteners)
- No emoji, no headers, no bold — Signal supports markdown but keep it minimal
- Skip replies that lack standalone context, skip low-engagement quotes
- 4-second pause between messages to respect Signal rate limits
- If a tweet text is too long, excerpt the first ~120 chars and add `…`

### Rate limiting

Signal-cli enforces ~1 message per 4 seconds. The delivery script handles this with `time.sleep(4)` between sends. For 15 tweets, total delivery time is ~60 seconds. This is fine for a background cron job — it runs at 09:00 UTC with no user waiting on it.

## Delivery to Discord (Weekly)

### Weekly aggregation from daily cache

Every daily cron run saves its full delivery content (prose + raw tweet links) to:

```
/opt/data/cron/output/7c85dd238709/YYYY-MM-DD_hh-mm-ss.md
```

The weekly Discord digest reads the last 7 daily files from this cache, aggregates them, and synthesizes a cross-week thematic summary. No re-fetching of tweets needed.

### Workflow

1. **Run aggregator**: `python3 /opt/data/skills/social-media/x-digest/scripts/weekly_aggregator.py > /tmp/weekly_raw.txt`
2. **Read `/tmp/weekly_raw.txt`** — prose + links from the past 7 days
3. **Synthesize cross-week themes**: merge repeated topics across days into a single narrative
4. **Deduplicate links**: each tweet URL appears once in the week's links section, keyed to its first appearance
5. **Post to Discord** with paragraph-style thematic summaries + deduplicated links section
6. **Log** to `/opt/data/logs/digest-runs.jsonl` with status `weekly_ok`

### Format rules (Discord weekly)

- Paragraph-style prose per theme (2-3 sentences max — keep it tight)
- Conversational but tight — no filler, no press-release language
- Raw links section at the end, max 15 links
- **TOTAL MUST BE UNDER 1900 CHARACTERS** — Discord truncates at 2000
- Header: `AI High Signal Weekly — Jul 11-17, 2026`
- No markdown headers (#), no emoji dividers, no bold
- If the prose is too long, cut prose sentences, not links

## Cron Jobs

Two cron jobs, two platforms:

| Job | ID | Schedule | Deliver | Format |
|-----|----|----------|---------|--------|
| **Daily Signal** | `7c85dd238709` (update) | `0 9 * * *` | Signal (via `scripts/daily_signal_delivery.py`) | Individual tweets per message, `hermes send` |
| **Weekly Discord** | New | `0 9 * * 0` | `discord:1492908666871877833` | Thematic prose + deduplicated links |

**Update existing daily job**: change `deliver` from `discord:1492908666871877833` to `origin` (this Signal chat), and switch to `no_agent=True` mode running the delivery script.

**Create new weekly job**: same skills (`x-digest`, `unified-digest-themes`), Sunday 09:00 UTC, delivers to Discord #x-tweet-digests, uses the weekly aggregator script.

## Weekly Aggregation

Every daily cron run saves its full delivery content (prose + raw tweet links) to:

```
/opt/data/cron/output/7c85dd238709/YYYY-MM-DD_hh-mm-ss.md
```

These files are an effective daily digest cache — no need to re-fetch tweets for weekly synthesis.

### Aggregator script

`scripts/weekly_aggregator.py` reads the last 7 daily output files and prints their prose + links sections. Run it from the skill directory:

```bash
python3 /opt/data/skills/social-media/x-digest/scripts/weekly_aggregator.py > /tmp/weekly_raw.txt
```

Output format:
```
=== YYYY-MM-DD ===
[prose summary]

Links (N):
@handle: https://x.com/i/status/ID
...
```

### Weekly cron job pattern

A weekly aggregator (e.g., Sunday 09:00 UTC delivering to Discord):

1. **Run aggregator**: `python3 /opt/data/skills/social-media/x-digest/scripts/weekly_aggregator.py > /tmp/weekly_raw.txt`
2. **Read `/tmp/weekly_raw.txt`** — contains prose + all links from the past 7 days
3. **Synthesize cross-week themes**: merge repeated topics across days into a single narrative. E.g., Kimi K3 appearing Thursday and Friday gets one section, not two.
4. **Deduplicate links**: a tweet URL appearing on multiple days appears only once in the final links section. Use the earliest day's entry.
5. **Log to** `/opt/data/logs/digest-runs.jsonl` with status `weekly_ok`

### Pitfalls

- **Inconsistent prose quality**: Some days only have a run summary (OAuth failure status, validation note) rather than full thematic prose. The aggregator handles gracefully — those days produce shorter entries.
- **File-mutation verifier noise**: Cron output files sometimes end with "File-mutation verifier" warnings. The aggregator strips these via regex.
- **Missing days gracefully**: If no output file exists for a date, skip it and note the gap in the weekly summary. Don't fail.
- **Link deduplication is the LLM's job**: The aggregator preserves all links from each day. The LLM must deduplicate in the synthesis step — a tweet that appeared in 3 daily digests gets included once in the weekly links section.
- **`since_time`/`until_time` for twitterapi.io**: When you need to fetch tweets from a specific date range directly (not from cache), pass Unix timestamps in the advanced_search query: `since_time:1762732800 until_time:1763337600`. These are standard Twitter search operators supported by twitterapi.io.

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
- **Signal delivery requires `hermes send`**, not the cron's auto-delivery. Individual tweets per message, 4s delay between sends. `daily_signal_delivery.py` handles this. Do NOT try to format Signal messages as multi-tweet prose blocks — Signal truncates them.
- **Signal group chat IDs**: use `hermes send --list signal` to discover group IDs. They look like `signal:Group Name  [group:<base64>=]`. Pass the full name string as the `--to` target.
- **No silent failure check**: `hermes send` returns exit code 0 on success. If a message fails (rate limit, network), the return code is 1. The delivery script logs failures but does not retry — retrying a rate-limited send would compound the problem.

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
| `scripts/weekly_aggregator.py` | Weekly aggregation — reads 7 days of cron output files, extracts prose + links for LLM synthesis. Located in skill directory, run via absolute path. |
| `scripts/daily_signal_delivery.py` | Daily Signal delivery — fetches tweets, picks top ~15 by engagement, sends each as individual `hermes send` message with 4s delay. Designed for `no_agent=True` cron mode. |