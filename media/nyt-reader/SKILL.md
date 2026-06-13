---
name: nyt-reader
description: Read NYTimes headlines, articles, and the publisher-narrated MP3s using the user's authenticated browser session. Emits structured JSON for downstream skills. 30-day article/audio cache, 1-hour cache for headlines.
version: 0.1.0
author: Nick Lange
license: Apache-2.0
metadata:
  hermes:
    tags: [nyt, nytimes, news, audio, narrated, json, agent-cli]
    required_environment_variables: [NYT_A, NYT_S, NYT_JKIDD, NYT_PURR, NYT_B_SID]
    required_commands: [python, nyt]
---

# nyt-reader

Programmatic NYTimes access via the user's logged-in session cookies. Exposes four CLI commands; all emit JSON for consumption by other agents/skills.

## When to Use — natural-language → command

| User says… | Run |
|---|---|
| "today's NYT headlines", "what's on the NYT front page" | `nyt headlines` |
| "show me NYT stories that have audio" | `nyt headlines --audio-only` |
| "read the NYT article at <url>" | `nyt article <url>` |
| "download the NYT audio for this story" | `nyt audio <url> --download` |
| "is this NYT story in my reading list" | `nyt saved --url <url>` |

## Setup

**One-time, by the human** (the agent cannot do this — requires a browser):

1. Sign in to https://www.nytimes.com.
2. DevTools → **Network** → click any `samizdat-graphql.nytimes.com` request → copy the full `Cookie:` header value.
3. From this skill's directory: `pbpaste | python scripts/set_cookie.py` (extracts the 5 named cookies and writes `.env` mode 600). A bookmarklet for one-click copy:

   ```
   javascript:(()=>{navigator.clipboard.writeText(document.cookie).then(()=>alert('NYT cookies copied ('+document.cookie.length+' chars).'));})();
   ```

**One-time install**:

```bash
python3 -m pip install --user -e /path/to/agent-skills/media/nyt-reader
```

When the skill prints `SESSION_EXPIRED` (exit code 2), repeat the cookie capture.

## Agent invocation

```bash
nyt headlines --limit 10
nyt headlines --audio-only          # only stories with a narrated MP3
nyt article https://www.nytimes.com/2026/06/07/.../...html
nyt audio   https://www.nytimes.com/2026/06/07/.../...html --download
nyt saved --url https://www.nytimes.com/2026/06/07/.../...html
```

Fallback if `nyt` is not on PATH: `python3 -m nyt_reader.cli headlines --limit 10`.

Add `--json-errors` to mirror failures as structured JSON on stdout.

## Politeness

- 350ms ± 100ms jittered spacing between origin fetches (`NYT_REQUEST_SPACING_MS`).
- Single-threaded; no parallel fetches.
- Adaptive backoff on 429/503, respects `Retry-After`.
- Per-invocation fetch budget of 200 (`NYT_MAX_FETCHES`).

## Cache

`media/nyt-reader/cache/` by default; override with `NYT_CACHE_DIR`. Tiered TTL: articles + MP3s 30d, headlines + saved-status 1h.

## Tests

`pip install -e ".[dev]" && pytest` — unit tests use synthetic fixtures and HTTP mocks (no live calls, no copyrighted NYT content in the repo).
