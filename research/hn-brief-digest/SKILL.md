---
name: hn-brief-digest
description: Fetch and reformat daily Hacker News summaries from HN Brief (hn-brief.com) into thematic digests with full Article + Discussion format per story. Uses browser automation to access the JS SPA, clicks "articles" view for detailed story summaries.
version: 4.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hacker-news, hn, digest, research, daily]
    related_skills: [unified-digest-themes, jargon, x-digest]
---

# HN Brief Digest

Fetches daily Hacker News summaries from HN Brief and reformats into themed digests.
Group and top-summarize — hn-brief.com provides the article/discussion text. Do NOT rewrite individual story summaries.

## ⚠️ Critical Pitfalls

1. **Domain**: `hn-brief.com`, NOT `hnbrief.net`
2. **JS SPA**: `web_extract`/`curl` won't work. Use `browser_navigate` → click "articles" → extract. Fallback: `node /opt/data/scripts/fetch-hn-brief.mjs` then use SPA's `fetch('summaries/YYYY/MM/DD.md')`.
3. **Atomic cache writes only**: use terminal `printf ... > path`, NOT write_file.

## 🔄 Workflow

### Step 0: Check Cache
- Compute yesterday's date: `date -d 'yesterday' +%Y/%m/%d`
- If `/opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt` exists and < 30 days old, read and deliver it. Skip to Step 7.
- If not cached, proceed.

### Step 1: Fetch Content
- `browser_navigate` to `https://hn-brief.com/`
- Wait for networkidle, click "articles" button
- Extract the page content (articles view with per-story summaries)
- Fallback: `node /opt/data/scripts/fetch-hn-brief.mjs` then SPA fetch
- Last resort: salvage from `/opt/data/cron/output/<hn-brief-job-id>/` prior runs

### Step 2: Parse Stories
- Each story needs Article + Discussion text from hn-brief.com
- Preserve original wording — your job is grouping, not rewriting

### Step 3: Assign Themes
- Load `unified-digest-themes` skill for the canonical 12-theme taxonomy
- Group stories by theme. Use primary-signal rule for overlaps.
- Format: story number, title (domain), points, comments, then Article/Discussion blocks

### Step 4: Write Top Summary
- Level 1: One sentence — biggest story or dominant mood
- Level 2: Few paragraphs covering major themes and their significance

### Step 5: Run Jargon Detection
- Load `jargon` skill, read registry via skill_view
- Scan all story text for known terms
- Append `**Jargon:**` line with kindergarten definitions; skip saturated terms
- Mark newly discovered terms with 🆕

### Step 6: Save to Cache (MANDATORY)
- Pipe the FULL formatted digest to: `python3 /opt/data/scripts/digest-cache-write hn-brief $(date -d 'yesterday' +%Y-%m-%d)`
- This writes atomically to `/opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt`
- This cache feeds weekly, monthly, and popularity tracker jobs.

### Step 7: Deliver
- Final response is auto-delivered by cron. Do NOT use send_message.
- Plain text, no markdown.

## 📚 References

- `references/cloudflare-bypass.md` — Verified Playwright pattern
- `references/hn-brief-backfill.md` — Backfill procedure for missing cache dates
- `references/cache_inventory.md` — Known gaps and cleanup
- `references/ai-ml-research-sub-themes.md` — Granular AI/ML sub-theme guidance
- `references/date-navigation.md` — Date picker usage for popularity tracking
- `references/thread-evidence.md` — Design history
