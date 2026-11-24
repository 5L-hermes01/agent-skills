# Validation Spec: hn-brief-dataset + HN Brief daily email
# Last updated: 2026-11-22
# Change: dataset reader skill + SMTP daily email job (07:45 NY, retries 08:15/09:15)

## Positive Checks (MUST be present)

- [ ] Answers cite story title **and** article URL; HN discussion link present when the question is about discussion
- [ ] Story order matches `stories[]` rank order in the day JSON
- [ ] Dates come from `latest.json` / `archive.json`, never from file mtime
- [ ] Email subject is exactly `HN Brief — <date>` (em dash, date = dataset date)
- [ ] Email body ordering: header line → 20 headlines in rank order (title, points, comments, article URL, HN link) → separator → `DIGEST` → digest text
- [ ] Message is multipart with a plain-text part **and** an HTML part whose links are clickable (`<a href>` for article and HN)
- [ ] Email is built from the dataset only; headline count = `quality.storyCount` capped at 20
- [ ] Rendered email cached at `/opt/data/cache/hn-brief-email/<date>.txt` and `.html`
- [ ] `last_sent` recorded in `/opt/data/state/hn-brief-email.last-sent.json` after each successful send, and a repeat run for the same date exits without sending
- [ ] Three cron runs exist, all `timezone: America/New_York`: 07:45, 08:15, 09:15

## Negative Checks (MUST NOT be present)

- [ ] No invented stories, URLs, points, or HN item ids
- [ ] No content read from `runs/`
- [ ] No write attempted into `/opt/shared_space/hn-brief-data`
- [ ] No email sent when `latest.json.date` != today (America/New_York)
- [ ] No email sent when `quality.digestValid` is false
- [ ] No email sent twice for the same date
- [ ] No Discord delivery for anything in this pipeline
- [ ] `SMTP_PASSWORD` never appears in the log, the rendered cache, stdout, the repo, or chat

## Format-Specific Checks

- [ ] Plain-text part stays readable at phone width (no tables, no markdown syntax needed)
- [ ] STARTTLS used on port 587 (implicit TLS only if the configured port is 465)
- [ ] Stale-run warning appears in answers after 08:00 America/New_York when the latest date is not today
- [ ] A real send failure exits 2 so the failure notice reaches Signal; a missing-briefing/duplicate/missing-credential run exits 0 silently
