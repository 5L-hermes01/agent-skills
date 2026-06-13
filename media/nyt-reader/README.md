# nyt-reader

Programmatic NYTimes access (headlines, articles, narrated MP3s) using the user's authenticated browser session. JSON output for agent consumption. 30-day article/audio cache.

> **Not affiliated with The New York Times.** Uses the user's own session and follows polite rate-limiting (350ms spacing, backoff on 429/503). Respect NYT's terms of service and your account's usage limits.

## Install

```sh
cd media/nyt-reader
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

For tests: `pip install -e ".[dev]"`.

## Configure cookies (~10 s with bookmarklet)

1. Sign in to https://www.nytimes.com.
2. Bookmarklet (drag into your bookmarks bar, click while on nytimes.com):

   ```
   javascript:(()=>{navigator.clipboard.writeText(document.cookie).then(()=>alert('NYT cookies copied to clipboard ('+document.cookie.length+' chars).'));})();
   ```
3. Pipe it into the helper:

   ```sh
   pbpaste | python scripts/set_cookie.py     # macOS
   xclip -o -selection clipboard | python scripts/set_cookie.py   # Linux X11
   wl-paste | python scripts/set_cookie.py    # Linux Wayland
   ```

   The helper extracts `nyt-a`, `NYT-S`, `nyt-jkidd`, `nyt-purr`, `nyt-b-sid` and writes them as `NYT_A`/`NYT_S`/`NYT_JKIDD`/`NYT_PURR`/`NYT_B_SID` in `.env` (mode 600).

Session cookies expire. When `nyt` exits with `SESSION_EXPIRED` (exit code 2), repeat.

### Cookie helper reference

```sh
python scripts/set_cookie.py                 # interactive paste
pbpaste | python scripts/set_cookie.py       # pipe from clipboard
python scripts/set_cookie.py cookie.txt      # from a file
python scripts/set_cookie.py --dry-run       # print what would be written
```

## Use

```sh
nyt headlines --limit 10                     # JSON: top 10 articles
nyt headlines --audio-only                   # only articles with narrated MP3s
nyt article https://www.nytimes.com/2026/...html
nyt audio https://www.nytimes.com/2026/...html --download
nyt saved --url https://www.nytimes.com/2026/...html
```

Add `--json-errors` to mirror failures as structured JSON on stdout.

## Agents

Three entrypoint files: `SKILL.md` (Claude), `AGENTS.md` (Codex/generic), `GEMINI.md` (Gemini CLI). All point at the same `nyt` CLI and JSON contract (`schemas/*.schema.json`).

## How auth works

NYT requires:
- **5 named cookies** captured from a logged-in browser session (the helper script extracts them).
- **3 static request headers**: `nyt-app-type: project-vi`, `nyt-app-version: 0.0.5`, and a long `nyt-token` blob. The token is a public client identifier baked into the NYT web bundle — embedded in the skill. If NYT rotates it, set `NYT_TOKEN=` in `.env` to override.

## Cache

`cache/` by default; override with `NYT_CACHE_DIR`. Tiered TTL:
- Article body, MP3 file: **30 days**
- Headlines, saved-status: **1 hour**

`--no-cache` bypasses on read and write.

## Tests

```sh
pip install -e ".[dev]"
pytest
```

All unit tests use synthetic fixtures and HTTP mocks. No live network calls, no copyrighted NYT content in the repo.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `SESSION_EXPIRED` (exit 2) | Cookies expired | Re-run the bookmarklet + `pbpaste \| python scripts/set_cookie.py` |
| Persistent 403 on GraphQL | NYT rotated `nyt-token` | Inspect a fresh request in DevTools, copy the `nyt-token` header value into `.env` as `NYT_TOKEN=...` |
| `NOT_FOUND` on `nyt article` | NYT changed `__NEXT_DATA__` shape | Open the page, check the script tag id, update `_NEXT_DATA_RE` in `src/nyt_reader/article.py` |
| Headlines empty | `LegacyPersonalizedPackagesQuery` hash rotated | Capture a new HAR, extract the new `sha256Hash`, update `HASH_LEGACY_PERSONALIZED_PACKAGES` in `src/nyt_reader/headlines.py` |
| Rate-limit 429s | Cold-cache fan-out | Raise `NYT_REQUEST_SPACING_MS` or lower `NYT_MAX_FETCHES`. Backoff is automatic. |
