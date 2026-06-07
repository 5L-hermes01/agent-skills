---
name: ft-reader
description: Read FT.com articles, top headlines per section, audio (MP3) links, and the user's MyFT saved articles using their authenticated browser session. Emits structured JSON for downstream skills. 30-day article/audio cache, 1-hour cache for headline/list endpoints.
version: 0.1.0
author: Nick Lange
license: Apache-2.0
metadata:
  hermes:
    tags: [ft, financial-times, news, audio, myft, json, agent-cli]
    required_environment_variables: [FT_COOKIE]
    required_commands: [python, ft]
---

# ft-reader

Programmatic FT.com access via the user's logged-in session cookies. Exposes four CLI commands; all emit JSON on stdout for consumption by other agents/skills.

## When to Use — natural-language → command

| User says… | Run |
|---|---|
| "give me today's FT headlines", "what's new on FT", "top FT stories in <section>" | `ft headlines [--section <id>] [--limit N]` |
| "read me the FT article at <url>", "summarize this FT piece", "what does this FT article say" | `ft article <uuid-or-url>` |
| "download the FT audio for this", "give me the MP3 of this FT article", "is there a listen-to version" | `ft audio <uuid-or-url> [--download]` |
| "show my FT saved list", "what's in my MyFT", "queue up everything I saved for listening" | `ft myft [--download-audio]` |

## Setup

**One-time, by the human** (the agent cannot do this — it requires a browser):

1. Sign in to https://app.ft.com.
2. DevTools → **Network** → click any `app-api.ft.com` request → copy the full `Cookie:` header value.
3. From this skill's directory: `pbpaste | python scripts/set_cookie.py` (writes `.env` mode 600). Bookmarklet in `README.md` for one-click copy.

**One-time install** (operator or a Hermes setup script):

```bash
python3 -m pip install --user -e /path/to/agent-skills/media/ft-reader
# This puts the `ft` command on PATH and installs the `requests` dep.
```

When the skill prints `SESSION_EXPIRED` (exit code 2), the human repeats steps 1–3.

## Agent invocation

Hermes Agent (and any agent driving this through a `terminal()` / shell tool) should call the installed `ft` binary directly. All commands print JSON to stdout, errors to stderr, with non-zero exit on failure.

```bash
ft headlines --section tech --limit 5
ft article <uuid-or-ft-url>
ft audio <uuid-or-ft-url> --download
ft myft --limit 50 --download-audio
```

If `ft` is not on PATH, fall back to:

```bash
python3 -m ft_reader.cli headlines --section tech --limit 5
```

Add `--json-errors` to mirror errors as structured `{"error": {...}}` JSON on stdout (useful when parsing tool output programmatically).

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
