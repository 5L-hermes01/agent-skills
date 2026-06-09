# wsj-reader

Programmatic Wall Street Journal access (print-edition headlines, articles, narrated MP3s) using the user's authenticated browser session. JSON output for agent consumption. 30-day article/audio cache.

> **Not affiliated with Dow Jones / The Wall Street Journal.** Uses the user's own session and follows polite rate-limiting (400ms spacing, backoff on 429/503). Respect WSJ's terms of service and your account's usage limits.

## Install

```sh
cd media/wsj-reader
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

For tests: `pip install -e ".[dev]"`.

## Configure cookies (~10s with bookmarklet)

WSJ's session is split across many cookies (`DJSESSION`, `djcs_*`, Adobe `AMCV_*`, datadome, consent flags…) and the **full Cookie header is required** — no minimal subset works.

1. Sign in to https://www.wsj.com.
2. Bookmarklet:

   ```
   javascript:(()=>{navigator.clipboard.writeText(document.cookie).then(()=>alert('WSJ cookies copied to clipboard ('+document.cookie.length+' chars).'));})();
   ```
3. Pipe to the helper:

   ```sh
   pbpaste | python scripts/set_cookie.py     # macOS
   xclip -o -selection clipboard | python scripts/set_cookie.py   # Linux X11
   wl-paste | python scripts/set_cookie.py    # Linux Wayland
   ```

   The helper validates the cookie length and writes `WSJ_COOKIE=...` into `.env` (mode 600).

Session cookies expire. When `wsj` exits with `SESSION_EXPIRED` (exit code 2), repeat.

### Cookie helper reference

```sh
python scripts/set_cookie.py                 # interactive paste
pbpaste | python scripts/set_cookie.py       # pipe from clipboard
python scripts/set_cookie.py cookie.txt      # from a file
python scripts/set_cookie.py --dry-run       # print what would be written
```

## Use

```sh
wsj headlines                                 # most recent print edition
wsj headlines --date 20260608                 # specific date
wsj headlines --section business --limit 5
wsj article https://www.wsj.com/finance/...html
wsj audio https://www.wsj.com/finance/...html --download
wsj audio WP-WSJ-0003640310 --download        # skip the article fetch
```

Add `--json-errors` to mirror failures as structured JSON on stdout.

## Agents

Three entrypoint files: `SKILL.md` (Claude), `AGENTS.md` (Codex/generic), `GEMINI.md` (Gemini CLI). All point at the same `wsj` CLI and JSON contract (`schemas/*.schema.json`).

## How audio works

Unlike FT (inlines `audio.url` on MyFT items) and NYT (inlines `featuredAudio.asset.fileUrl` in GraphQL responses), WSJ requires a two-step resolve:

1. **Article page** → extract `articleData.id` (e.g. `WP-WSJ-0003640310`) from `__NEXT_DATA__`.
2. **`video-api.shdsvc.dowjones.io/api/legacy/find-all-videos?type=read-to-me&query={id}`** → JSON with the canonical audio UUID and creation date.
3. **Construct** `https://m.wsj.net/audio/{YYYYMMDD}/{uuid}/1/ele-{id-lower}-full.mp3` — public CDN, no auth on the MP3 itself.

`wsj audio` does all three steps. The resolve result is cached 30d alongside the MP3 so a re-run is free.

## Cache

`cache/` by default; override with `WSJ_CACHE_DIR`. Tiered TTL:
- Article body, MP3 file, audio-resolve metadata: **30 days**
- Headlines (per-day print edition page): **1 hour**

`--no-cache` bypasses on read and write.

## Tests

```sh
pip install -e ".[dev]"
pytest
```

All unit tests use synthetic fixtures and HTTP mocks. No live network calls, no copyrighted WSJ content in the repo.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `SESSION_EXPIRED` (exit 2) | Cookies expired or only a partial set was pasted | Re-run the bookmarklet + `pbpaste \| python scripts/set_cookie.py`. WSJ needs the **full** Cookie header. |
| `NOT_FOUND` from `wsj headlines` | No print edition for the chosen date (weekend, holiday) | Omit `--date` to walk back, or pick a recent weekday |
| `NOT_FOUND` from `wsj article` | WSJ changed `__NEXT_DATA__` shape | Open the page, inspect the script tag, update `_NEXT_DATA_RE` in `src/wsj_reader/_next_data.py` |
| `wsj audio` returns `available: false` | Article has no read-to-me MP3 yet (recently published or not narrated) | Wait, or skip. The pipeline tolerates missing audio. |
| Persistent 401 from `wsj article` | Missing browser-like headers stripped by an intermediate proxy | The client already sends `Sec-Fetch-*` and `Referer`. Confirm no MITM proxy is rewriting requests. |
| Rate-limit 429s | Cold-cache fan-out | Raise `WSJ_REQUEST_SPACING_MS` (default 400) or lower `WSJ_MAX_FETCHES` (default 200). Backoff is automatic. |
