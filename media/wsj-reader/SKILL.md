---
name: wsj-reader
description: Read Wall Street Journal print-edition headlines, articles, and the publisher-narrated MP3s ("read-to-me") using the user's authenticated browser session. Emits structured JSON for downstream skills. 30-day article/audio cache, 1-hour cache for headlines.
version: 0.2.0
author: Nick Lange
license: Apache-2.0
metadata:
  hermes:
    tags: [wsj, wall-street-journal, news, audio, read-to-me, json, agent-cli]
    required_environment_variables: [WSJ_COOKIE]
    required_commands: [python, wsj]
---

# wsj-reader

Programmatic WSJ access via the user's logged-in session cookies. Exposes three CLI commands; all emit JSON for consumption by other agents/skills.

## When to Use — natural-language → command

| User says… | Run |
|---|---|
| "today's WSJ", "WSJ print edition headlines", "what's on the front page" | `wsj headlines` |
| "WSJ business section today" | `wsj headlines --section business` |
| "read the WSJ article at <url>" | `wsj article <url>` |
| "download the WSJ audio for this story" | `wsj audio <url-or-WP-WSJ-id> --download` |

## Setup

**One-time, by the human** (requires a browser):

1. Sign in to https://www.wsj.com.
2. DevTools → **Network** → click any `www.wsj.com` request → copy the full `Cookie:` header value.
3. From this skill's directory: `pbpaste | python scripts/set_cookie.py` (writes `.env` mode 600). A bookmarklet for one-click copy:

   ```
   javascript:(()=>{navigator.clipboard.writeText(document.cookie).then(()=>alert('WSJ cookies copied ('+document.cookie.length+' chars).'));})();
   ```

**One-time install**:

```bash
python3 -m pip install --user -e /path/to/agent-skills/media/wsj-reader
```

When the skill prints `SESSION_EXPIRED` (exit code 2), repeat the cookie capture. WSJ's full Cookie header is required — no minimal subset works.

## Agent invocation

```bash
wsj headlines                                 # most recent headlines (GraphQL)
wsj headlines --date 20260608                 # specific date
wsj headlines --section business --limit 5
wsj article https://www.wsj.com/finance/...html
wsj audio https://www.wsj.com/finance/...html --download
wsj audio WP-WSJ-0003640310 --download        # bypass the article fetch
```

Fallback if `wsj` is not on PATH: `python3 -m wsj_reader.cli headlines`.

Add `--json-errors` to mirror failures as structured JSON on stdout.

## How audio works

WSJ doesn't inline audio URLs in either headlines or articles. The flow:

1. Article page → extract `articleData.id` (e.g. `WP-WSJ-0003640310`) from `__NEXT_DATA__`.
2. `GET video-api.shdsvc.dowjones.io/api/legacy/find-all-videos?type=read-to-me&query={id}` → JSON with the canonical audio `id` (UUID) and creation date.
3. Construct `https://m.wsj.net/audio/{YYYYMMDD}/{uuid}/1/ele-{id-lower}-full.mp3` — public CDN, no auth on the MP3 itself.

The skill caches the audio-resolution call for 30 days alongside the MP3.

## Politeness

- 400ms ± 100ms jittered spacing between origin fetches (`WSJ_REQUEST_SPACING_MS`). WSJ is more sensitive than NYT/FT — keep the gap.
- Single-threaded; no parallel fetches.
- Adaptive backoff on 429/503, respects `Retry-After`.
- Per-invocation fetch budget of 200 (`WSJ_MAX_FETCHES`).
- Browser-like headers (`Sec-Fetch-*`, `Referer`, `Origin`) are required by WSJ's edge — included automatically.

## Cache

`media/wsj-reader/cache/` by default; override with `WSJ_CACHE_DIR`. Tiered TTL: articles + MP3s + audio-resolve 30d, headlines 1h.

## Tests

`pip install -e ".[dev]" && pytest` — unit tests use synthetic fixtures and HTTP mocks (no live calls, no copyrighted WSJ content in the repo).

## Version History

- 0.2.0 (2026-07-15): WSJ's shared-data.dowjones.io GraphQL endpoint now requires cookies.
  Added `Cookie` header to GraphQL transport. Both transports still work; the cookie
  is no longer optional for the GraphQL path.
