# GEMINI.md — wsj-reader

Entrypoint for the Gemini CLI. Same contract as `SKILL.md` (Claude) and `AGENTS.md` (Codex/generic).

## Invocation

```
wsj headlines [--date YYYYMMDD] [--section front|business|world|popular] [--limit N] [--no-cache] [--json-errors]
wsj article <url> [--no-cache] [--json-errors]
wsj audio <url-or-WP-WSJ-id> [--download] [--no-cache] [--json-errors]
```

JSON to stdout with `"schema_version": 1`. Errors to stderr; `--json-errors` also mirrors them as `{"error": {...}}` on stdout.

Exit codes: `0` ok, `1` other, `2` `SESSION_EXPIRED`, `3` `NOT_FOUND`, `4` `NETWORK`.

## Setup

1. `pip install -e .` in `media/wsj-reader/`.
2. Capture the full browser Cookie header: DevTools → Network → click any `www.wsj.com` request → Request Headers → copy `Cookie:` value. Then `pbpaste | python scripts/set_cookie.py`.
3. Optional tuning env vars: `WSJ_CACHE_DIR`, `WSJ_REQUEST_SPACING_MS`, `WSJ_MAX_FETCHES`, `WSJ_USER_AGENT`.

## Output schemas

`schemas/*.schema.json` define each command's output shape.

## Politeness

400ms ± jitter between origin fetches; single-threaded; adaptive backoff on 429/503; per-invocation fetch budget of 200. Browser-like `Sec-Fetch-*` headers required by WSJ — included automatically.

## Caching

Tiered file cache in `cache/` (override via `WSJ_CACHE_DIR`). Article + MP3 + audio-resolve 30d; headlines 1h.
