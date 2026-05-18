# HN Brief Digest — Thread Evidence & Design History

## Origin Session

- **Session**: `20260511_020220_440e4b3b` (Discord thread, May 11, 2026)
- **Original request**: [NJL] wanted a daily skill to read HN Brief summaries, run at 22:00 EST
- **Format**: Both the thematic summary (digest) AND the top-20 articles with per-story summaries
- **Pattern**: Follow x-digest formatting — theme-grouped, plain text, no markdown/emojis
- **Caching**: `/opt/data/cache/hn-brief/` — organize by date

## Issue Discovery Session

- **Session**: `20260518_041016_8d5a10e1` (Discord thread, May 18, 2026)
- **What happened**: The cron job delivered a thin/condensed digest instead of the full Article + Discussion format from hn-brief.com
- **Root cause**:
  1. The cron used `hnbrief.net` (wrong domain — should be `hn-brief.com`)
  2. No skill was attached to the cron — the original `hn-brief-digest` skill had been deleted
  3. The cron prompt was vague ("summarize the key stories") — each model session interpreted this differently
  4. hn-brief.com is now a JS SPA — requires browser tools (curl/web_extract don't work)

## Fix Applied (May 18, 2026)

1. Created `hn-brief-digest` skill (v3.0.0) with:
   - 🎯 Objective section defining the quality bar
   - 🌐 Correct URL: hn-brief.com (not hnbrief.net)
   - 📝 Exact output format: Title → Article: → Discussion:
   - 🖥️ Browser workflow for JS SPA
   - ⚠️ Known pitfalls documented
2. Updated cron job `37017ee4425f` to:
   - Attach the `hn-brief-digest` skill
   - Fix the domain reference
   - Reference the skill for format/objective
3. Submitted PR #22 to agent-skills repo

## Key Lessons for Future Maintenance

- Never let a cron job run without an attached skill — the skill IS the format spec
- If a site's URL changes (hnbrief.net → hn-brief.com), update BOTH the skill AND the cron prompt
- hn-brief.com is a JS SPA — always use browser tools, never curl/web_extract
- Click the "articles" button for detailed per-story summaries — the default digest view is condensed
