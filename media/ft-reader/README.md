# ft-reader

Programmatic FT.com access (headlines, articles, audio MP3s, MyFT saved list) using the user's authenticated browser session. JSON output for agent consumption. 30-day article/audio cache.

> **Not affiliated with the Financial Times.** Uses the user's own session and follows polite rate-limiting (350ms spacing, backoff on 429/503). Respect FT's terms of service and your account's usage limits.

## Install

```sh
cd media/ft-reader
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

(For tests: `pip install -e ".[dev]"`.)

## Configure cookies (once per session lifetime)

The simplest path is to paste your entire browser Cookie header — MyFT and a few other endpoints require a coupled set of cookies that can't be reduced to a small named subset.

### Fast path (~10s with bookmarklet)

1. In your browser, while signed in to https://app.ft.com, run this bookmarklet (drag into your bookmarks bar, then click):

   ```
   javascript:(()=>{navigator.clipboard.writeText(document.cookie).then(()=>alert('FT cookies copied to clipboard ('+document.cookie.length+' chars).'));})();
   ```

2. In a terminal:

   ```sh
   pbpaste | python scripts/set_cookie.py     # macOS
   xclip -o -selection clipboard | python scripts/set_cookie.py   # Linux X11
   wl-paste | python scripts/set_cookie.py    # Linux Wayland
   ```

   The helper parses the cookie string and writes `FT_COOKIE=...` plus the four legacy named vars into `.env` (mode 600).

### Manual path (~1 min, no bookmarklet)

1. Sign in to https://app.ft.com.
2. DevTools → **Network** tab → reload → click any `app-api.ft.com` request → **Request Headers** → copy the full `Cookie:` value.
3. `python scripts/set_cookie.py` and paste, then Ctrl-D. (Or `python scripts/set_cookie.py path/to/saved.txt`.)

Session cookies expire. When `ft` exits with `SESSION_EXPIRED` (exit code 2), repeat.

### Cookie helper reference

```sh
python scripts/set_cookie.py                 # interactive paste
pbpaste | python scripts/set_cookie.py       # pipe from clipboard
python scripts/set_cookie.py cookie.txt      # from a file
python scripts/set_cookie.py --dry-run       # print what would be written, don't touch .env
```

Accepts a raw `name=value; ...` blob, a `Cookie: ...` header line, multi-line `Set-Cookie:` headers, or a JSON object keyed by cookie name.

### Legacy 4-cookie mode

If you only need headlines/article/audio (not MyFT), you can instead set `FT_SESSION_S`, `FT_CLIENT_SESSION_ID`, `FT_APP_USER`, `FT_CSRF` from DevTools → Application → Cookies. `ft myft` will likely return `SESSION_EXPIRED` in this mode — use `FT_COOKIE` for full coverage.

## Use

```sh
ft headlines --section world --limit 5     # JSON: top 5 World headlines
ft article <uuid-or-ft-url>                # JSON: title, byline, body, audio
ft audio <uuid-or-ft-url> --download       # download MP3 to ./cache/
ft myft --limit 50 --download-audio        # JSON list of saved articles + MP3s
```

Add `--json-errors` to mirror failures as structured JSON on stdout (handy for agents).

## Agents

This skill ships with three entrypoint files so any agent can drive it:

- `SKILL.md` — Claude Code / Claude.ai
- `AGENTS.md` — Codex, Cursor, Aider, generic
- `GEMINI.md` — Gemini CLI

All three point at the same `ft` CLI and document the same JSON contract (`schemas/*.schema.json`).

## Cache

`cache/` in this directory by default. Override with `FT_CACHE_DIR=/some/path`. TTL is tiered:

- Article body, MP3 file: **30 days**
- `/structure/v14` (front + sections), MyFT list, audio-availability check: **1 hour**

`--no-cache` bypasses on read and write.

## Tests

```sh
pip install -e ".[dev]"
pytest
```

All unit tests use synthetic fixtures and HTTP mocks. No live network calls, no copyrighted FT content in the repo.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `SESSION_EXPIRED` (exit 2) on any command | Cookies have expired or were never pasted | Re-run the bookmarklet + `pbpaste \| python scripts/set_cookie.py` |
| `ft myft` returns `SESSION_EXPIRED` while `ft headlines` works | Using the legacy 4-cookie env vars instead of `FT_COOKIE` | Set `FT_COOKIE` to the full browser Cookie header — MyFT needs the coupled cookie set |
| Headlines look wrong/empty for a section | FT changed the `/structure/v14` response shape; teasers now in a new field | Inspect `cache/<hash>.json` for the structure dump and adjust `_teasers_for_section()` in `src/ft_reader/headlines.py` |
| `ft article` returns title/body but `byline` is `null` | FT changed byline tree node shape (`data` vs `value`) | Both keys are handled in `_flatten_byline()`; if it breaks again, log the raw `byline` field and extend the helper |
| Persistent 429 / 503 errors | Rate-limit pressure from a cold-cache fan-out, or CDN flagging | Raise `FT_REQUEST_SPACING_MS` (default 350) or lower `FT_MAX_FETCHES` (default 200). Backoff is automatic for the in-process burst. |
| Article returns `{"error": "access denied"}` mid-run | Mid-session cookie rotation by FT | Re-paste cookies. Long-running scripts should catch `SESSION_EXPIRED` and prompt the user. |
| FT changes API version (`/structure/v14` → `/v15`) | Endpoint moved | Update `STRUCTURE_URL` in `src/ft_reader/headlines.py`; bump the package version. |

## Files

```
ft-reader/
  SKILL.md   AGENTS.md   GEMINI.md   README.md
  .env.sample   .gitignore   pyproject.toml
  src/ft_reader/
    cli.py  client.py  cache.py
    headlines.py  article.py  audio.py  myft.py
  schemas/{headlines,article,audio,myft}.schema.json
  tests/
    fixtures/{structure,article,myft}.json   # synthetic only
    test_*.py
```
