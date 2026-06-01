---
name: hn-brief-digest
description: Fetch and reformat daily Hacker News summaries from HN Brief (hn-brief.com) into thematic digests with full Article + Discussion format per story. Uses browser automation to access the JS SPA, clicks "articles" view for detailed story summaries.
version: 4.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hacker-news, hn, digest, research, daily]
    related_skills: [unified-digest-themes, jargon, x-digest]
---

# HN Brief Digest

Fetches daily Hacker News summaries from [HN Brief](https://hn-brief.com) and reformats them into thematic digests with the **Article + Discussion** format.

## 🎯 Objective (Why This Skill Exists)

This skill exists to deliver a **consistent HN Brief digest** to Discord daily at 22:00 EST. The output structure is:

### Output Structure

1. **📋 Top Summary** — A condensed, AI-written overview of the day's Hacker News, written at **two levels of detail**:
   - **Level 1**: One sentence capturing the biggest story or dominant mood of the day
   - **Level 2**: A few paragraphs summarizing the major themes and notable stories, written conversationally

2. **📁 Themed Sections** — Stories grouped by the **unified cross-platform theme system**.
   - Load the `unified-digest-themes` skill for the canonical 7-theme taxonomy and AI & ML Research sub-theme reference.
   - See `references/ai-ml-research-sub-themes.md` for granular sub-theme guidance within AI & ML Research.

3. **🔤 Jargon** — After the last themed section, include a jargon block with decoded technical terms from the day's stories.

   Load the `jargon` skill (references/jargon-registry.json) to scan all story titles, article summaries, and discussion text for known jargon. For each term found, append a labeled definition:

   ```
   **Jargon:** 🎒 LLM = a smart computer brain that understands words. AGI = a computer that can think like a human.
   ```

   Use kindergarten-level definitions for general audience. Mark newly discovered terms with 🆕.

4. **📰 Per-Story Format** — Each story under its theme:
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
## ⚠️ Known Pitfalls
1. **Wrong domain**: `hnbrief.net` does not work. Always use `hn-brief.com`
2. **JS SPA**: hn-brief.com is a JavaScript single-page app. `web_extract` or `curl` will NOT get the full content. Preferred path: use the Playwright helper script (`scripts/fetch-hn-brief.mjs`) to bypass Cloudflare, then use the SPA's own inline `fetch('summaries/...')` calls to obtain article/digest markdown.
3. **No plain .md access**: The old `https://hn-brief.com/summaries/YYYY/MM/DD.md` URLs no longer serve markdown directly. They return Cloudflare challenges/403. All content must be obtained through an authenticated SPA session.
4. **Cookie/Cloudflare**: The site requires a Cloudflare challenge. A headless Chromium session visiting `https://hn-brief.com` and waiting for `networkidle` establishes the required cookies so the SPA's own `fetch()` calls succeed.
5. **Tool set varies**: Not all Hermes environments expose `browser_navigate`/`browser_click`/`browser_scroll`/`browser_console`. Do not hard-fail when those are missing; use the Playwright script path or cron-output fallback instead.
6. **Articles view matters**: The "articles" tab provides per-story Article + Discussion sections used by this skill. The default "digest" view is insufficient.
7. **Format drift**: Each run of the cron job without this skill attached will produce different output. This skill **must** be attached to the cron job to maintain consistent output format.
8. **No inline backfill in cron**: Do NOT use shell hacks as workarounds inside cron prompts. Cron sessions should call the standalone backfill script as a one-off job.
9. **Atomic cache writes only**: Cache must always use terminal-based atomic writes. Do not rely on write_file for cache — stream drops are silent and corrupt backups.

## 📝 Full Output Structure

### 1. Top Summary (condensed, two levels)

Write a short overview at the top of the digest:

```
HN Brief Daily Digest — YYYY-MM-DD

Level 1: One sentence on the biggest story or dominant trend.

Level 2: A few conversational paragraphs covering the major themes, notable stories, and what they mean. Write this yourself — condense from the hn-brief.com content.
```

### 2. Themed Sections

Stories grouped under the **unified cross-platform theme system** (canonical source: `unified-digest-themes` skill):

| # | Theme | Description |
|---|-------|-------------|
| 1 | AI & ML Research | Models, architectures, training, benchmarks, agents, papers — see [sub-theme reference](references/ai-ml-research-sub-themes.md) for granular breakdown |
| 2 | Developer Tools & Infrastructure | IDEs, workflows, compute, platforms, agent tooling |
| 3 | Hardware & IoT | Chips, devices, embedded, robotics, edge inference |
| 4 | Security & Privacy | Vulnerabilities, breaches, encryption, prompt injection, alignment safety |
| 5 | Industry & Business | Funding, companies, products, pricing, policy, regulation |
| 6 | Science & Technology | Physics, bio, space, general science |
| 7 | Community & Culture | Meta-discussions, events, nostalgia, offbeat, hot takes |

### 3. Per-Story Format (within each theme)

```
N. Title (domain.com) X points | Y comments

Article:
[full article summary from hn-brief.com]

Discussion:
[full discussion summary from hn-brief.com]
```

Each story's **Article** and **Discussion** sections come verbatim from hn-brief.com — do not rewrite them. Your editorial work is the **top summary** and the **theme assignment**.

## 💾 Caching (MANDATORY)

You MUST save formatted digests to cache. This feeds the weekly and monthly summary jobs.

All fetched content is cached locally at `/opt/data/cache/hn-brief/`:

```
/opt/data/cache/hn-brief/
└── YYYY/
    └── MM/
        └── DD/
            └── formatted-digest.txt
```

**Important rules:**
1. **Check before fetching**: Compute yesterday's date. If `/opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt` exists, skip fetching and deliver the cached version.
2. **Save after formatting**: After formatting the digest (Step 6 below), ALWAYS write the finalized formatted text to `/opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt` using terminal(`mkdir -p ...` + `python ...`) to avoid dropped tool-call streams. See **Cache Reliability** below.
3. **Cache is valid for 30 days.** After 30 days, re-fetch.
4. **Use yesterday's date** (summaries are for previous day's news, so YYYY-MM-DD = today - 1 day).

### Cache Reliability
A known failure mode is a partial `write_file` stream drop (e.g. `Connection reset by peer`). Use a terminal-based atomic write instead:

```bash
mkdir -p /opt/data/cache/hn-brief/YYYY/MM/DD
printf '%s\n' "$(cat)" > /opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt
```

Implementation steps:
1. Write the full final formatted digest text to a temp file:
   `/tmp/hn-brief-formatted.txt`
2. Run: `mkdir -p /opt/data/cache/hn-brief/YYYY/MM/DD`
3. Rename: `mv /tmp/hn-brief-formatted.txt /opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt`
4. Verify: re-read the file and confirm it exists and size>0 before delivering.

## 🔄 Workflow

### Step 0: Check Cache
- Compute yesterday's date (summaries are for previous day's news)
- Check if `/opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt` exists
- If cached and < 30 days old, read the file and deliver it directly (skip all browser steps)
- If not cached, proceed with Step 1

### Step 1: Fetch HN Brief Content
If dedicated browser tools exist in this environment, use them as the primary path (`browser_navigate` → `"articles"` → scroll/extract). If not, use the established fallback:
1. Run the Playwright helper: `node /opt/data/scripts/fetch-hn-brief.mjs`
2. That script confirms the SPA's markdown endpoints: `summaries/YYYY/MM/DD.md` and `summaries/YYYY/MM/DD-digest.md`
3. Use the same Playwright session to call the SPA's own `fetch()` for the target date and write the fetched markdown to `/tmp/hn-brief-<YYYY-MM-DD>.md` for parsing.
4. **Cron-output salvage**: If both browser tooling and the Playwright script fail, inspect nearby cron-output files under `/opt/data/cron/output/`. Many failed/partial runs still contain the formatted digest text or the skill prompt payload. Look for:
   - `/opt/data/cron/output/<hn-brief-job-id>/<YEAR-MONTH-DAY>_*.md`
   - Extract the formatted digest portion after `## Response` — it may already be themed+formatted from a previous run.
   - Treat this as a viable source because the agent in that run already loaded the skill, formatted, and cached the work. Reuse it rather than redoing the live fetch.
5. Only declare a date unavailable after the cron-output salvage also fails.

### Step 2: Parse Stories and Extract Article/Discussion
- Parse the markdown fetched for the target date.
- Each story must have both **Article:** and **Discussion:** text from hn-brief.com.
- Preserve the original hn-brief.com wording; your job is grouping, not rewriting.

### Step 5: Run Jargon Detection
- Load the `jargon` skill
- Read `references/jargon-registry.json` via skill_view(name='jargon', file_path='references/jargon-registry.json')
- Scan all story titles, article summaries, and discussion text from your formatted output for known jargon terms
- Append a **Jargon:** line at the end of the formatted digest with kindergarten-level definitions
- For newly detected terms not in the registry, mark with 🆕

### Step 6: Save to Cache (MANDATORY)
- Create cache directory: `mkdir -p /opt/data/cache/hn-brief/YYYY/MM/DD/`
- Write the FULL formatted digest (including jargon block) to `/opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt`
- Use write_file() for this — it ensures the file is written atomically

### Step 7: Deliver
- The cron job's final response is automatically delivered — do NOT use send_message
- Plain text only (no markdown formatting, emojis, or bold)

## 🧪 Verification Checklist

Before finalizing output, verify:
- [ ] Domain used is `hn-brief.com`, NOT `hnbrief.net`
- [ ] Articles view is loaded (not just the digest view)
- [ ] **Top summary** is present with two levels of detail
- [ ] Stories are grouped under the **7 unified themes** (from `unified-digest-themes` skill, not hn-brief.com's themes)
- [ ] Each story has both **Article:** and **Discussion:** sections
- [ ] Per-story content comes verbatim from hn-brief.com (not rewritten)
- [ ] Cache directory structure is maintained

## 📚 References

- **Canonical theme taxonomy**: Load the `unified-digest-themes` skill — it is the single source of truth for all theme definitions across HN Brief, X-Digest, AI-News, and arXiv jobs.
- [Backfill Operating Procedure](references/hn-brief-backfill.md) — How and when to backfill missing cache dates using `/opt/data/scripts/hn-brief-backfill.py`, including cache-first checks and atomic write verification.
- [Cache Inventory](references/cache_inventory.md) — Known missing-date patterns, root-cause notes, and half-finished job cleanup.
- [AI & ML Research Sub-Theme Reference](references/ai-ml-research-sub-themes.md) — Granular breakdown of "AI & ML Research" into Models, Training, Benchmarks, Agents, and Papers sub-themes.
- [Date Navigation](references/date-navigation.md) — How to use the 📅 date picker to load historical dates for popularity tracking and backfill.
- [Thread Evidence & Design History](references/thread-evidence.md) — Original design session, issue discovery, and lessons learned.
- [Cloudflare + SPA Bypass](references/cloudflare-bypass.md) — Verified Playwright pattern for fetching HN Brief markdown when direct tool access is unavailable or returns 403.

### Digest Pipeline Architecture

The HN Brief digest system has four tiers of cron jobs feeding from the same file cache:

| Tier | Job | Schedule | Channel | Source |
|------|-----|----------|---------|--------|
| Daily | hn-brief-daily-digest | 22:00 UTC | #hacker-news | Browser scrape hn-brief.com |
| Weekly | hn-brief-weekly-digest | Sun 23:00 UTC | #weekly-hn-brief | 7 cached formatted-digest.txt files |
| Monthly | hn-brief-monthly-digest | 1st 20:00 UTC | #monthly-hn-brief | ~30 cached formatted-digest.txt files |
| PopTracker | hn-brief-popularity-tracker | Sun 21:00 UTC | #weekly-hn-brief | Re-scrapes hn-brief via 📅 date picker for a date ~30 days back |

**Cache dependency**: Weekly, monthly, and popularity jobs all rely on the daily job writing `/opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt`. This is why caching is MANDATORY in the workflow above.

**Popularity tracking**: Re-scrape an old date via the 📅 date picker + articles view. Compare current points/comments vs cached publish-time values. Report which stories gained the most traction. No API keys — just the browser and cache.

**Cache-failure fallback**: If a downstream job finds no cache for its target date(s), it must not simply stop. It should attempt a direct date-picker scrape first, and only declare the date unavailable after that fetch fails.

**Backfill trigger**: Any day with no `/opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt` should be treated as a backfill candidate. Priority for filling: dates expressly used by weekly/monthly/popularity jobs before any other minor dates.

**Cache-failure fallback**: If the popularity tracker finds no cache for its target date(s), it MUST NOT simply report “no cache data available” and stop. Instead, it should fall back to scraping the date directly via the date picker/`browser` tool so the check still produces useful output. Only after a direct fetch attempt should it declare the date unavailable.
