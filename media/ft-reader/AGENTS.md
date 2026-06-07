# AGENTS.md — ft-reader

Entrypoint for any agent following the AGENTS.md convention (Codex, Cursor, Aider, generic CLI agents). Mirrors `SKILL.md` and `GEMINI.md`.

## Invocation

After `pip install -e .` in this directory and a populated `.env`, agents should call the `ft` CLI directly:

```
ft headlines [--section <id>] [--limit N] [--no-cache] [--json-errors]
ft article <uuid-or-url> [--no-cache] [--json-errors]
ft audio <uuid-or-url> [--download] [--no-cache] [--json-errors]
ft myft [--limit N] [--download-audio] [--no-cache] [--json-errors]
```

All commands print one JSON object to stdout with `"schema_version": 1`. Errors go to stderr; `--json-errors` mirrors them to stdout as `{"error": {"code", "message"}}`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | other / unexpected |
| 2 | `SESSION_EXPIRED` — cookies stale; user must re-paste |
| 3 | `NOT_FOUND` — bad UUID/URL |
| 4 | `NETWORK` — upstream/timeout/persistent 429 |

## Required environment

In `.env` (or process env): `FT_COOKIE` — full browser Cookie header for `app.ft.com`. (Legacy: `FT_SESSION_S` + `FT_CLIENT_SESSION_ID` + `FT_APP_USER` + `FT_CSRF` works for everything except `ft myft`.) Optional: `FT_CACHE_DIR`, `FT_REQUEST_SPACING_MS` (default 350, min 100, max 5000), `FT_MAX_FETCHES` (default 200), `FT_USER_AGENT`.

## Output schemas

See `schemas/headlines.schema.json`, `schemas/article.schema.json`, `schemas/audio.schema.json`, `schemas/myft.schema.json`.

## Non-interactive guarantee

The CLI never prompts. Cookie problems surface as `SESSION_EXPIRED` (exit 2) on stderr.

## Caching

Tiered file cache in `cache/`. Article + MP3 = 30d. Headlines + MyFT + audio-availability = 1h. `--no-cache` bypasses on read+write.

## Example agent workflow

```sh
# Pull today's tech-section headlines as JSON
ft headlines --section tech --limit 3 > /tmp/headlines.json

# Extract first UUID and download its MP3
uuid=$(jq -r '.sections[0].headlines[0].uuid' /tmp/headlines.json)
ft audio "$uuid" --download | jq '.local_path'
```
