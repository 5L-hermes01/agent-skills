---
name: waytoagi-reader
description: Read the 通往AGI之路 (WaytoAGI) Feishu wiki daily update log as structured JSON. No auth required — uses the public guest-mode SSR endpoint.
version: 0.1.0
author: Nick Lange
license: Apache-2.0
metadata:
  hermes:
    tags: [waytoagi, feishu, lark, wiki, china, ai-news, json, agent-cli]
    required_environment_variables: []
    required_commands: [python, waytoagi]
---

# waytoagi-reader

Programmatic access to the WaytoAGI Feishu wiki daily update log ("🎏 近 7 日更新日志"). Emits JSON for downstream agents/skills.

No authentication required — the wiki is publicly readable in guest mode. The skill fetches the SSR HTML, extracts the inline Feishu block-tree JSON, decodes AttributedText with apool mention-doc expansion, and renders the target section.

## When to Use — natural-language → command

| User says… | Run |
|---|---|
| "today's WaytoAGI updates", "近 7 日更新日志", "what's new on WaytoAGI" | `waytoagi update-log` |
| "WaytoAGI 6/18", "WaytoAGI June 18" | `waytoagi update-log --date '6 月 18 日'` |
| "flat list of recent WaytoAGI items" | `waytoagi update-log --flatten` |
| "WaytoAGI history", "older WaytoAGI entries", "全部更新日志" | `waytoagi update-log --archive` |
| "WaytoAGI on May 22, 2025" | `waytoagi update-log --archive --date '5 月 22 日'` |

## Setup

```bash
python3 -m pip install --user -e /path/to/agent-skills/media/waytoagi-reader
```

No `.env`, no cookies, no API key.

## Agent invocation

```bash
waytoagi update-log                              # full 7-day section, grouped by day
waytoagi update-log --date '6 月 18 日'           # one day from the 7-day window
waytoagi update-log --flatten                    # flat items[] for downstream pipes
waytoagi update-log --archive                    # full historical archive, grouped by month/day
waytoagi update-log --archive --date '5 月 22 日' # one historical day across all years
waytoagi update-log --heading '近 7 日更新日志'   # override heading match (defensive)
waytoagi update-log --fuzzy                      # substring heading match (fallback)
waytoagi update-log --no-cache                   # bypass the 5-minute raw-HTML cache
waytoagi update-log --refresh                    # bypass cache read, refresh stored entry
waytoagi update-log --emit-raw-blocks            # debugging: dump the full block dict
```

### Modes

- **Default (no flags)**: parses the "🎏 近 7 日更新日志" section of the main wiki page. ~7 days, grouped by day heading.
- **`--archive`**: follows the "历史更新" mention link in the main doc to the archive (auto-discovered, not hardcoded). Renders all months / all days; each day item gets a `month` field. 500+ days indexed across the year+ archive.

  **Archive coverage caveat**: Feishu's guest SSR only inlines nested block objects for a recent window of the archive doc (~the latest days). Older day headings reference child block ids that are absent from the payload entirely (client-side pagination), so those days render `items: []` and emit an accurate `[warn]` diagnostic — the content is not recoverable from the HTML, not a parser/encoding defect.
- **`--flatten`**: collapses `days[]` into a single `items[]` list. Each item gains `day` and `day_heading_id` fields. Use this when piping into the sibling `translate` skill or any downstream consumer that wants a flat feed.

Fallback if `waytoagi` is not on PATH: `python3 -m waytoagi_reader.cli update-log`.

## Output

`schemas/update_log.schema.json`. Days are heading-level blocks under the target section; items are the bullets/text/image/divider blocks attached to each day. Each item has `{id, type, title, url, summary}`; `title` and `url` are populated when the bullet contains a Feishu `mention_doc` link (the common case for daily entries).

The flat `--flatten` variant is intended for downstream `translate` pipes (sibling skill in this repo, `media/translate/`).

## Exit codes

| Code | Meaning | Recovery |
|---|---|---|
| 0 | OK | — |
| 3 | NOT_FOUND — heading text didn't match any heading block | Pass `--heading` with the current literal text, or open the page to see if it was renamed |
| 4 | Transient — fetch error, decode error, etc. | Retry |
| 5 | UPSTREAM_CONTRACT_BROKEN — heading found but section empty, or zero blocks parsed | Inspect with `--emit-raw-blocks`; Feishu likely changed SSR shape |

## Politeness

- One fetch per invocation under normal use.
- No parallel fetches.
- Default User-Agent is a modern Chrome string; override is not exposed yet (add if/when a tenant complains).

## Cache

Raw-HTML TTL cache (v0.1). Default 300s. Override with `WAYTOAGI_CACHE_DIR`, `WAYTOAGI_CACHE_RAW_TTL`. `--no-cache` bypasses; `--refresh` bypasses read but writes.

Feishu sends `Cache-Control: no-store` and no `ETag`/`Last-Modified`, so conditional revalidation is not currently possible. The two follow-on tiers (parsed-blocks, rendered JSON) are deliberately deferred — they're a JSON parse away from the raw tier.

## Translation

Out of scope for the reader itself, but a batch translator ships at `scripts/waytoagi-translate.py` — it reads `--flatten` JSON on stdin, batch-translates every Chinese `title`/`summary` through a local OpenAI-compatible server (default `qwen3.8` on `http://192.168.100.10:11434`), and emits the same document with `title_en`/`summary_en` siblings. Filesystem translation cache makes re-runs near-instant.

```bash
waytoagi update-log --flatten | waytoagi-translate.py --host http://192.168.100.10:11434 --model qwen3.8
waytoagi update-log --flatten | waytoagi-translate.py --latest-day   # daily digest: only most recent day
```

Env overrides: `WAYTOAGI_TRANSLATE_HOST`, `WAYTOAGI_TRANSLATE_MODEL`, `WAYTOAGI_TRANSLATE_CACHE` (default `$XDG_CACHE_HOME/waytoagi-translate`). `--no-cache` bypasses the cache. The sibling `translate` skill (`media/translate/`) also gained an `openai_compat` backend (set `TRANSLATE_BACKEND=openai_compat`, `TRANSLATE_OPENAI_HOST`, `TRANSLATE_OPENAI_MODEL`).

### Full article content

`scripts/waytoagi_content.py` fetches each linked article and translates its FULL body to English, preserving external (non-Feishu) hyperlinks as markdown `[label](url)`. Reads the translated `--flatten` JSON on stdin and adds `content_zh` / `content_en` to each item.

```bash
waytoagi update-log --flatten | waytoagi-translate.py ... | waytoagi_content.py --host http://192.168.100.10:11434 --model qwen3.8
```

External link note: the reader's default render drops `link` attribs (external URLs). `waytoagi_content.py` re-decodes them so they survive translation. Content + translation are cached by URL (`WAYTOAGI_CONTENT_CACHE`, default `$XDG_CACHE_HOME/waytoagi-content`); `--batch-chars` controls translation chunk size (default `WAYTOAGI_BATCH_CHARS` or 2000 source chars).

## Tests

`pip install -e ".[dev]" && pytest`. Synthetic fixtures only — no waytoagi content reproduced in the repo. See `LICENSING.md` for why.
