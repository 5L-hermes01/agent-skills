# GEMINI.md — nyt-reader

Entrypoint for the Gemini CLI. Same contract as `SKILL.md` (Claude) and `AGENTS.md` (Codex/generic).

## Invocation

```
nyt headlines [--limit N] [--audio-only] [--no-cache] [--json-errors]
nyt article <url> [--no-cache] [--json-errors]
nyt audio <url> [--download] [--no-cache] [--json-errors]
nyt saved [--url <url> ...] [--no-cache] [--json-errors]
```

JSON to stdout with `"schema_version": 1`. Errors to stderr; `--json-errors` also mirrors them as `{"error": {...}}` on stdout.

Exit codes: `0` ok, `1` other, `2` `SESSION_EXPIRED`, `3` `NOT_FOUND`, `4` `NETWORK`.

## Setup

1. `pip install -e .` in `media/nyt-reader/`.
2. Capture cookies: DevTools → Network → click any `samizdat-graphql.nytimes.com` request → Request Headers → Cookie. Then `pbpaste | python scripts/set_cookie.py` to extract the 5 named cookies into `.env`.
3. Optional tuning env vars: `NYT_TOKEN`, `NYT_CACHE_DIR`, `NYT_REQUEST_SPACING_MS`, `NYT_MAX_FETCHES`, `NYT_USER_AGENT`.

## Output schemas

`schemas/*.schema.json` define each command's output shape.

## Politeness

350ms ± jitter between origin fetches; single-threaded; adaptive backoff on 429/503; per-invocation fetch budget of 200.

## Caching

Tiered file cache in `cache/` (override via `NYT_CACHE_DIR`). Article + MP3 30d, headlines + saved-status 1h.
