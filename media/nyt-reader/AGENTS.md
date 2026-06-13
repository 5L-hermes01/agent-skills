# AGENTS.md — nyt-reader

Entrypoint for any agent following the AGENTS.md convention (Codex, Cursor, Aider, generic CLI agents). Mirrors `SKILL.md` and `GEMINI.md`.

## Invocation

After `pip install -e .` in this directory and a populated `.env`:

```
nyt headlines [--limit N] [--audio-only] [--no-cache] [--json-errors]
nyt article <url> [--no-cache] [--json-errors]
nyt audio <url> [--download] [--no-cache] [--json-errors]
nyt saved [--url <url> ...] [--no-cache] [--json-errors]
```

All commands print one JSON object to stdout with `"schema_version": 1`. Errors go to stderr; `--json-errors` mirrors them to stdout as `{"error": {"code", "message"}}`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | other / unexpected |
| 2 | `SESSION_EXPIRED` — cookies stale; user must re-paste |
| 3 | `NOT_FOUND` — bad URL / page missing __NEXT_DATA__ |
| 4 | `NETWORK` — upstream/timeout/persistent 429 |

## Required environment

In `.env` (or process env): `NYT_A`, `NYT_S`, `NYT_JKIDD`, `NYT_PURR`, `NYT_B_SID`. Optional: `NYT_TOKEN` (override embedded client token), `NYT_CACHE_DIR`, `NYT_REQUEST_SPACING_MS` (default 350, range 100–5000), `NYT_MAX_FETCHES` (default 200), `NYT_USER_AGENT`.

## Output schemas

See `schemas/headlines.schema.json`, `schemas/article.schema.json`, `schemas/audio.schema.json`, `schemas/saved.schema.json`.

## Non-interactive guarantee

The CLI never prompts. Cookie problems surface as `SESSION_EXPIRED` (exit 2) on stderr.

## Caching

Tiered file cache in `cache/`. Article + MP3 = 30d. Headlines + saved-status = 1h. `--no-cache` bypasses on read+write.

## Example agent workflow

```sh
# Pick the first audio-equipped headline and download its MP3.
nyt headlines --audio-only --limit 1 > /tmp/h.json
url=$(jq -r '.articles[0].url' /tmp/h.json)
nyt audio "$url" --download | jq '.local_path'
```
