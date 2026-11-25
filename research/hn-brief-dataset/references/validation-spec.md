# Validation Spec: hn-brief-dataset + HN Brief daily/weekly/monthly delivery
# Last updated: 2026-11-24
# Change: daily delivery now targets email AND the Discord Daily Channel
#         (#hacker-news); net-new weekly/monthly aggregators over the dataset.

## Positive Checks (MUST be present)

- [ ] Answers cite story title **and** article URL; HN discussion link present when the question is about discussion
- [ ] Story order matches `stories[]` rank order in the day JSON
- [ ] Dates come from `latest.json` / `archive.json`, never from file mtime
- [ ] Email subject is exactly `HN Brief — <date>` (em dash, date = dataset date)
- [ ] Email body ordering: header line → 20 headlines in rank order (title, points, comments, article URL, HN link) → separator → `DIGEST` → digest text
- [ ] Message is multipart with a plain-text part **and** an HTML part whose links are clickable (`<a href>` for article and HN)
- [ ] The same plain-text briefing is posted to Discord `#hacker-news` (1503214829509410887), chunked to ≤2000 chars per message
- [ ] Rendered email cached at `/opt/data/cache/hn-brief-email/<date>.txt` and `.html`
- [ ] `last_sent` recorded in `/opt/data/state/hn-brief-email.last-sent.json` **and** `/opt/data/state/hn-brief-discord.last-sent.json` after each successful send; a repeat run for the same date exits without re-sending to either target
- [ ] A partly-failed day re-attempts ONLY the target that failed (separate state files)
- [ ] Three email/Channel cron runs exist, all `timezone: America/New_York`: 07:45, 08:15, 09:15
- [ ] `hn-brief-weekly-aggregate` exists: `0 20 * * 0`, delivers to `discord:1507971737055264831`, local provider `ollama-qwen3.6:27b` / model `qwen3.8-27b-instruct`, script `hn-brief-weekly-prep.py`
- [ ] `hn-brief-monthly-aggregate` exists: `0 18 1 * *`, delivers to `discord:1507971842374111363`, same provider/model, script `hn-brief-monthly-prep.py`
- [ ] Weekly/monthly output first line names the window (`HN Brief Weekly — <first> to <last>`)
- [ ] Weekly/monthly cite title + article URL for every story and open with a Level 1 sentence then Level 2 paragraphs
- [ ] Weekly output ≤ 9000 chars, monthly ≤ 12000 chars
- [ ] Weekly/monthly corpus header carries `save_to:` and the job writes its digest there (`/opt/data/cache/hn-brief/{weekly,monthly}/…`)
- [ ] The corpus carries a per-story `article:` and `hn:` URL, and every `Link:`/`Discussion:` line in the digest is one of those, copied verbatim
- [ ] Delivery confirmed by READING THE CHANNEL BACK — the message in the channel is the digest itself (a `last_status=ok` / `delivered` run can still have posted an error string)

## Negative Checks (MUST NOT be present)

- [ ] No invented stories, URLs, points, or HN item ids
- [ ] No content read from `runs/`
- [ ] No write attempted into `/opt/shared_space/hn-brief-data`
- [ ] No delivery when `latest.json.date` != today (America/New_York)
- [ ] No delivery when `quality.digestValid` is false
- [ ] No duplicate delivery of a date to either target
- [ ] No repeated `Link:`/`Discussion:` URL across different stories — each story carries its own article and HN URL
- [ ] No tool-budget / `ran out of steps` / blocked-command text delivered in place of the digest
- [ ] No `Jargon:` section in weekly/monthly output (presentation is owned by `jargon-notify`)
- [ ] No seed/placeholder or thinking-model output (the aggregators must use the `-instruct` model, not `qwen3.8-27b`)
- [ ] A weekly/monthly run must not invent content for a day the corpus marks MISSING
- [ ] `SMTP_PASSWORD` and `DISCORD_BOT_TOKEN` never appear in the log, the rendered cache, stdout, the repo, or chat

## Format-Specific Checks

- [ ] Plain-text/Signal parts stay readable at phone width (no tables, no markdown syntax needed)
- [ ] STARTTLS used on port 587 (implicit TLS only if the configured port is 465)
- [ ] Stale-run warning appears in answers after 08:00 America/New_York when the latest date is not today
- [ ] Discord messages ≤ 2000 chars each; a long digest arrives as several ordered `(i/n)` messages
- [ ] A real transport failure exits 2 so `hermes cron list` shows `last_status=error`; a missing-briefing/duplicate run exits 0 silently
- [ ] Aggregator jobs run with `wrap_response: false` (no cron header/footer in the channel)
