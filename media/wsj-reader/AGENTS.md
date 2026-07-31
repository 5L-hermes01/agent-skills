# AGENTS.md — wsj-reader

Entrypoint for any agent following the AGENTS.md convention (Codex, Cursor, Aider, generic CLI agents). Mirrors `SKILL.md` and `GEMINI.md`.

## Invocation

After `pip install -e .` in this directory:

```
wsj headlines [--via homepage|graphql|html] [--collection ID|alias] [--date YYYYMMDD] [--section front|business|world|popular] [--limit N] [--no-cache] [--json-errors]
wsj article <url> [--no-cache] [--json-errors]
wsj audio <url-or-WP-WSJ-id> [--download] [--no-cache] [--json-errors]
wsj refresh-cookie [url] [--profile-dir DIR] [--headless] [--timeout SEC] [--dry-run]
```

All commands print one JSON object to stdout with `"schema_version": 1`. Errors go to stderr; `--json-errors` mirrors them to stdout as `{"error": {"code", "message"}}`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | other / unexpected |
| 2 | `SESSION_EXPIRED` — cookies stale on an authenticated path; user must re-paste `WSJ_COOKIE` |
| 3 | `NOT_FOUND` — bad URL / no edition for date / page missing `__NEXT_DATA__` |
| 4 | `NETWORK` — upstream/timeout/persistent 429 |

## Required environment

Optional for default `wsj headlines`; required for `wsj article`, `wsj audio <url>`, `wsj headlines --via=graphql`, and `wsj headlines --via=html`: `WSJ_COOKIE` — full browser Cookie header in `.env` or process env. Optional: `WSJ_CACHE_DIR`, `WSJ_REQUEST_SPACING_MS` (default 400, range 100–5000), `WSJ_MAX_FETCHES` (default 200), `WSJ_USER_AGENT`.

Optional for `wsj refresh-cookie`: install the browser extra and Chromium with `pip install -e ".[browser]" && python -m playwright install chromium`. The helper uses `WSJ_BROWSER_PROFILE_DIR` or `~/.wsj-reader-browser` for the persistent browser profile.

## Output schemas

All commands emit `schema_version: 1` JSON objects with stable top-level keys.

## Non-interactive guarantee

Normal reader commands never prompt. Cookie problems surface as `SESSION_EXPIRED` (exit 2) on stderr. `wsj refresh-cookie` is explicitly human/browser-assisted and may require signing in to the opened Chromium window.

## Caching

Tiered file cache in `cache/`. Article + MP3 + audio-resolve = 30d. Headlines = 1h. `--no-cache` bypasses on read+write.

## Example agent workflow

```sh
# Pick the first WSJ homepage story and grab its narrated MP3.
wsj headlines --limit 1 > /tmp/h.json
url=$(jq -r '.articles[0].url' /tmp/h.json)
wsj audio "$url" --download | jq '.local_path'
```
