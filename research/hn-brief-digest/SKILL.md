---
name: hn-brief-digest
description: Fetch and reformat daily Hacker News summaries from HN Brief (hn-brief.com) into thematic digests with full Article + Discussion format per story. Uses browser automation to access the JS SPA, clicks "articles" view for detailed story summaries.
version: 3.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hacker-news, hn, digest, research, daily]
    related_skills: [x-digest]
---

# HN Brief Digest

Fetches daily Hacker News summaries from [HN Brief](https://hn-brief.com) and reformats them into thematic digests with the **Article + Discussion** format.

## 🎯 Objective (Why This Skill Exists)

This skill exists to deliver a **consistent, high-fidelity HN Brief digest** to Discord daily at 22:00 EST. The output must match the hn-brief.com "articles" view verbatim — full story summaries followed by full discussion summaries — **not** condensed, re-summarized, or truncated.

> **CRITICAL: Do NOT re-summarize or condense.** The hn-brief.com site already does the AI-powered summarization. Your job is to **reformat** what hn-brief.com provides, not re-process it through another model. Mirror each story's content as-is.

## 🌐 URLs

- **Site**: `https://hn-brief.com` (NOT `hnbrief.net` — that domain does not work)
- **Daily Articles view**: Navigate to `https://hn-brief.com/`, click the **"articles"** button
- **Digest view**: Navigate to `https://hn-brief.com/`, default view shows the daily digest

## ⚠️ Known Pitfalls

1. **Wrong domain**: `hnbrief.net` does not work. Always use `hn-brief.com`
2. **JS SPA**: hn-brief.com is a JavaScript single-page app. `web_extract` or `curl` will NOT get the full content. You **must** use the browser tool:
   - `browser_navigate(url="https://hn-brief.com")`
   - Click the **"articles"** button for detailed story-by-story summaries with both Article and Discussion sections
   - Use `browser_scroll(direction="down")` to reveal more stories
   - Use `browser_console(expression='...')` to extract full page text via JavaScript DOM queries
3. **No .md file access**: The old `https://hn-brief.com/summaries/YYYY/MM/DD.md` URLs no longer work as plain markdown endpoints. All content is rendered client-side.
4. **Cookie/Cloudflare**: The site may require a Cloudflare challenge. Browser Use handles this automatically.
5. **Format drift**: Each run of the cron job without this skill attached will produce different output. This skill **must** be attached to the cron job to maintain consistent output format.

## 📝 Output Format

Each story in the digest must follow this exact format:

```
N. Title (domain.com) X points | Y comments

Article:
[full article summary as shown on hn-brief.com — do not condense or rewrite]

Discussion:
[full discussion summary as shown on hn-brief.com — do not condense or rewrite]
```

Stories should be grouped by theme (e.g., AI & ML, Developer Tools, Hardware, etc.) matching the hn-brief.com thematic grouping. The daily digest is capped at the top-20 stories from hn-brief.com.

## 💾 Caching

All fetched content is cached locally at `/opt/data/cache/hn-brief/`:

```
/opt/data/cache/hn-brief/
└── YYYY/
    └── MM/
        └── DD/
            ├── raw-page.html       (full browser snapshot)
            └── formatted-digest.txt
```

Cache is valid for 30 days. Check cache before fetching.

## 🔄 Workflow

### Step 0: Check Cache
- Compute yesterday's date (summaries are for previous day's news)
- Check if `/opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt` exists and is < 30 days old
- If cached, skip fetching and deliver the cached version

### Step 1: Navigate to HN Brief
- `browser_navigate(url="https://hn-brief.com")`
- Wait for page to fully render

### Step 2: Switch to Articles View
- Find and click the **"articles"** button/tab
- This reveals detailed per-story summaries with Article + Discussion sections

### Step 3: Extract Content
- Use `browser_scroll(direction="down")` repeatedly to load all stories
- Extract full page content via `browser_console(expression=JS_DOM_QUERY)`
- Save raw content to cache

### Step 4: Format Output
- Parse each story from the extracted content
- Follow the **Output Format** section above exactly
- Group by thematic categories
- Save formatted version to cache

### Step 5: Deliver
- The cron job's final response is automatically delivered — do NOT use send_message
- Plain text only (no markdown formatting, emojis, or bold)

## 🧪 Verification Checklist

Before finalizing output, verify:
- [ ] Domain used is `hn-brief.com`, NOT `hnbrief.net`
- [ ] Articles view is loaded (not just the digest view)
- [ ] Each story has both **Article:** and **Discussion:** sections
- [ ] Full summaries are preserved — nothing truncated or re-summarized
- [ ] Thematic grouping matches hn-brief.com categories
- [ ] Cache directory structure is maintained
