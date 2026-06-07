---
name: ft-reader
description: Read FT.com articles, top headlines per section, audio (MP3) links, and the user's MyFT saved articles using their authenticated browser session. Emits structured JSON for downstream skills. 30-day article/audio cache, 1-hour cache for headline/list endpoints.
version: 0.1.0
author: Nick Lange
metadata:
  hermes:
    tags: [ft, financial-times, news, audio, myft, json, agent-cli]
---

# ft-reader

Programmatic FT.com access via the user's logged-in session cookies. Exposes four CLI commands; all emit JSON on stdout for consumption by other agents/skills.

## When to Use

- "Give me today's FT headlines" → `ft headlines`
- "Read me the FT article at <url>" → `ft article <url>` (text) + `ft audio <url> --download` (MP3)
- "Summarize my MyFT saved list" / "queue up everything I saved for listening" → `ft myft --download-audio`

## Setup (one-time per session-cookie lifetime)

1. `cd media/ft-reader`
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -e .`
4. Sign in to https://app.ft.com in a browser. In DevTools → **Network**, click any request to `app-api.ft.com`, copy the full `Cookie:` header value.
5. `cp .env.sample .env` and paste it as `FT_COOKIE=...` (single line).
6. When the skill prints `SESSION_EXPIRED`, repeat steps 4–5.

> A legacy 4-cookie mode (`FT_SESSION_S` + 3 others) exists for headlines/article/audio only — `ft myft` requires the full `FT_COOKIE` blob.

## Commands

All commands print JSON to stdout with `schema_version: 1`. Errors go to stderr. Use `--json-errors` to also emit a structured `{"error": {...}}` object on stdout. Exit codes: `0` ok, `2` session expired, `3` not found, `4` upstream/network, `1` other.

### `ft headlines`

Top headlines per section. Fetches `/structure/v14` (cached 1h) then hydrates each teaser UUID via `/__content/v4/article/{uuid}` (cached 30d). Use `--section` to scope; default fans out across all 32 sections.

```
ft headlines --section world --limit 5
ft headlines                           # all sections, 5 each (cold cache: ~1 min, hot: instant)
ft headlines --no-cache                # force refresh
```

### `ft article <uuid-or-url>`

Single article, normalized. Accepts a bare UUID or any FT URL containing one.

```
ft article 11111111-1111-1111-1111-111111111111
ft article https://www.ft.com/content/11111111-1111-1111-1111-111111111111
```

### `ft audio <uuid-or-url>`

Resolve and optionally download the auto-synthesized MP3 attached to an article (when FT has generated one).

```
ft audio <uuid>                # check availability only
ft audio <uuid> --download     # also fetch + cache the MP3
```

Output includes `local_path` when `--download` is set and audio exists.

### `ft myft`

The user's MyFT saved-articles list. Each item already includes inline audio metadata.

```
ft myft --limit 50
ft myft --download-audio       # also download every available MP3 to cache
```

## Output JSON shapes

See `schemas/*.json` for full JSON Schemas. Quick examples:

```json
// ft headlines
{
  "schema_version": 1,
  "fetched_at": "2026-06-07T05:00:00Z",
  "sections": [
    {"id": "world", "name": "World",
     "headlines": [{"uuid": "...", "title": "...", "standfirst": "...",
                    "url": "...", "published": "...", "audio_available": true}]}
  ]
}
```

## Politeness

- 350ms ± 100ms jittered spacing between article/audio fetches (`FT_REQUEST_SPACING_MS`).
- Single-threaded; no parallel fetches.
- Adaptive backoff on 429/503, respects `Retry-After`.
- Per-invocation fetch budget of 200 (`FT_MAX_FETCHES`).

## Cache

`media/ft-reader/cache/` by default; override with `FT_CACHE_DIR`. Tiered TTL: articles + MP3s 30d, headlines + MyFT lists + audio-checks 1h.

## Tests

`pip install -e ".[dev]" && pytest` — unit tests use synthetic fixtures and HTTP mocks (no live calls, no copyrighted FT content in the repo).
