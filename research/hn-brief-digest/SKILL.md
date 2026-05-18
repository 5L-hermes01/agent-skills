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

This skill exists to deliver a **consistent HN Brief digest** to Discord daily at 22:00 EST. The output structure is:

### Output Structure

1. **📋 Top Summary** — A condensed, AI-written overview of the day's Hacker News, written at **two levels of detail**:
   - **Level 1**: One sentence capturing the biggest story or dominant mood of the day
   - **Level 2**: A few paragraphs summarizing the major themes and notable stories, written conversationally

2. **📁 Themed Sections** — Stories grouped by the **unified cross-platform theme system** (also used by X-Digest, Papers, etc.):
   - AI & ML Research
   - Developer Tools & Infrastructure
   - Hardware & IoT
   - Security & Privacy
   - Industry & Business
   - Science & Technology
   - Community & Culture

3. **📰 Per-Story Format** — Each story under its theme:
   ```
   N. Title (domain.com) X points | Y comments

   Article:
   [full article summary from hn-brief.com]

   Discussion:
   [full discussion summary from hn-brief.com]
   ```

> **Note on content**: The hn-brief.com site provides the article and discussion summaries. Your job is to **group and top-summarize** — write the condensed top summary, assign stories to the correct cross-platform theme, and present their hn-brief.com content underneath. Do not rewrite the individual story summaries.

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

## 📝 Full Output Structure

### 1. Top Summary (condensed, two levels)

Write a short overview at the top of the digest:

```
HN Brief Daily Digest — YYYY-MM-DD

Level 1: One sentence on the biggest story or dominant trend.

Level 2: A few conversational paragraphs covering the major themes, notable stories, and what they mean. Write this yourself — condense from the hn-brief.com content.
```

### 2. Themed Sections

Stories grouped under these unified cross-platform themes:

| # | Theme | Description |
|---|-------|-------------|
| 1 | AI & ML Research | Models, benchmarks, training, papers |
| 2 | Developer Tools & Infrastructure | IDE, workflows, compute, platforms |
| 3 | Hardware & IoT | Chips, devices, embedded, robotics |
| 4 | Security & Privacy | Vulnerabilities, breaches, encryption |
| 5 | Industry & Business | Funding, companies, products, policy |
| 6 | Science & Technology | Physics, bio, space, general science |
| 7 | Community & Culture | HN meta, debates, nostalgia, offbeat |

### 3. Per-Story Format (within each theme)

```
N. Title (domain.com) X points | Y comments

Article:
[full article summary from hn-brief.com]

Discussion:
[full discussion summary from hn-brief.com]
```

Each story's **Article** and **Discussion** sections come verbatim from hn-brief.com — do not rewrite them. Your editorial work is the **top summary** and the **theme assignment**.

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
- [ ] **Top summary** is present with two levels of detail
- [ ] Stories are grouped under the **7 unified themes** (not hn-brief.com's themes)
- [ ] Each story has both **Article:** and **Discussion:** sections
- [ ] Per-story content comes verbatim from hn-brief.com (not rewritten)
- [ ] Cache directory structure is maintained

## 📚 References

- [Thread Evidence & Design History](references/thread-evidence.md) — Original design session, issue discovery, and lessons learned. Read this to understand why the skill is structured this way and what issues occurred before.
