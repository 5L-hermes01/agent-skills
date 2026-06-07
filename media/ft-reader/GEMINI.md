# GEMINI.md — ft-reader

Entrypoint for the Gemini CLI. Same contract as `SKILL.md` (Claude) and `AGENTS.md` (Codex/generic).

## Invocation

```
ft headlines [--section <id>] [--limit N] [--no-cache] [--json-errors]
ft article <uuid-or-url> [--no-cache] [--json-errors]
ft audio <uuid-or-url> [--download] [--no-cache] [--json-errors]
ft myft [--limit N] [--download-audio] [--no-cache] [--json-errors]
```

JSON to stdout with `"schema_version": 1`. Errors to stderr; `--json-errors` also mirrors them as `{"error": {...}}` on stdout.

Exit codes: `0` ok, `1` other, `2` `SESSION_EXPIRED`, `3` `NOT_FOUND`, `4` `NETWORK`.

## Setup

1. `pip install -e .` in `media/ft-reader/`.
2. `cp .env.sample .env` and set `FT_COOKIE` to the full browser Cookie header value (DevTools → Network → click any `app-api.ft.com` request → Request Headers → Cookie). Legacy `FT_SESSION_S`/`FT_CLIENT_SESSION_ID`/`FT_APP_USER`/`FT_CSRF` work for everything except `ft myft`.
3. Optional tuning env vars: `FT_CACHE_DIR`, `FT_REQUEST_SPACING_MS`, `FT_MAX_FETCHES`, `FT_USER_AGENT`.

## Output schemas

`schemas/*.schema.json` define each command's output shape.

## Politeness

350ms ± jitter between article/audio fetches; single-threaded; adaptive backoff on 429/503; per-invocation fetch budget of 200.

## Caching

Tiered file cache in `cache/` (override via `FT_CACHE_DIR`). Article + MP3 30d, headlines + MyFT + audio-check 1h.
