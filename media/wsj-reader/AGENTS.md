# AGENTS.md — wsj-reader

Entrypoint for any agent following the AGENTS.md convention (Codex, Cursor, Aider, generic CLI agents). Mirrors `SKILL.md` and `GEMINI.md`.

## Invocation

After `pip install -e .` in this directory and a populated `.env`:

```
wsj headlines [--date YYYYMMDD] [--section front|business|world|popular] [--limit N] [--no-cache] [--json-errors]
wsj article <url> [--no-cache] [--json-errors]
wsj audio <url-or-WP-WSJ-id> [--download] [--no-cache] [--json-errors]
```

All commands print one JSON object to stdout with `"schema_version": 1`. Errors go to stderr; `--json-errors` mirrors them to stdout as `{"error": {"code", "message"}}`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | other / unexpected |
| 2 | `SESSION_EXPIRED` — cookies stale; user must re-paste `WSJ_COOKIE` |
| 3 | `NOT_FOUND` — bad URL / no edition for date / page missing `__NEXT_DATA__` |
| 4 | `NETWORK` — upstream/timeout/persistent 429 |

## Required environment

In `.env` (or process env): `WSJ_COOKIE` — full browser Cookie header. Optional: `WSJ_CACHE_DIR`, `WSJ_REQUEST_SPACING_MS` (default 400, range 100–5000), `WSJ_MAX_FETCHES` (default 200), `WSJ_USER_AGENT`.

## Output schemas

See `schemas/headlines.schema.json`, `schemas/article.schema.json`, `schemas/audio.schema.json`.

## Non-interactive guarantee

The CLI never prompts. Cookie problems surface as `SESSION_EXPIRED` (exit 2) on stderr.

## Caching

Tiered file cache in `cache/`. Article + MP3 + audio-resolve = 30d. Headlines = 1h. `--no-cache` bypasses on read+write.

## Example agent workflow

```sh
# Pick the first WSJ front-page story and grab its narrated MP3.
wsj headlines --section front --limit 1 > /tmp/h.json
url=$(jq -r '.articles[0].url' /tmp/h.json)
wsj audio "$url" --download | jq '.local_path'
```
