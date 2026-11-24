---
name: hn-brief-dataset
description: "Query the local HN Brief dataset: today, history, search."
version: 1.1.0
author: Hermes Agent 01
license: MIT
metadata:
  hermes:
    tags: [hacker-news, hn, dataset, daily, research, local-data, email]
    related_skills: [hn-brief-digest, grounded-citations]
---

# HN Brief Dataset (local, read-only) + daily email

Answer HN questions from the machine-readable dataset a pipeline on lunarBeacon
writes daily at ~07:13 America/New_York, and ship the same briefing by email at
07:45. No scraping, no browser, no guessing.

## Data root

`/opt/shared_space/hn-brief-data` (read-only mount). Never write to it.

```
latest.json            {date, runId, path}      ← always start here
archive.json           [{date, path, runId, storyCount}, ...] newest first
daily/YYYY/MM/DD.json  full day: date, generatedAt, runId, source, model,
                       digest (long essay), quality{storyFailures, storyCount,
                       digestValid}, stories[] in rank order
daily/YYYY/MM/DD.md    ready-made Markdown of the same day
daily/YYYY/MM/DD-digest.md   Markdown digest only
runs/                  raw debugging traces — IGNORE, not the product
```

Story fields: `id`, `title`, `url`, `points`, `num_comments`, `postType`,
`summary` (the article), `discussion_summary` (the HN comments).
HN discussion link: `https://news.ycombinator.com/item?id=<id>`.

## Scripts (shipped with this skill)

`scripts/hn-brief-data.py` — reader; use it instead of hand-parsing (~60 KB/day):

```bash
python3 <skill>/scripts/hn-brief-data.py latest          # today, all 20 stories
python3 <skill>/scripts/hn-brief-data.py top 5 [--date 2026-11-18]
python3 <skill>/scripts/hn-brief-data.py search "rust" --days 7 --snippets
python3 <skill>/scripts/hn-brief-data.py day 2026-11-21 --full
python3 <skill>/scripts/hn-brief-data.py digest [--date D]
python3 <skill>/scripts/hn-brief-data.py days            # published dates
```

Any subcommand accepts `--json`. Prefer the scripts over reading JSON inline:
the digest alone is ~15 KB, easy to truncate or mis-parse by hand.

`scripts/hn-brief-email.py` — the daily email (deterministic, no LLM).
`--dry-run` renders without sending, `--force` ignores the already-sent record,
`--to` overrides the recipient (default `nick.lange@gmail.com`).

`scripts/smtp-diagnose.py` — transport triage: prints the credential sources,
banner, EHLO capabilities, STARTTLS certificate and the raw AUTH exchange with
the server's own response codes. Never prints the password. Run it first on any
send failure.

## Daily email job

| Piece | Value |
|---|---|
| Subject | `HN Brief — <date>` (em dash) |
| Body | header → 20 headlines in rank order (points, comments, article URL, HN link) → `DIGEST` → full digest |
| Format | multipart: plain text + simple HTML with clickable links |
| Cron | three runs, `timezone: America/New_York` — 07:45 (main), 08:15 and 09:15 (retries) |
| Entry point | `HERMES_HOME/scripts/hn-brief-email.py` (real-file shim) → this skill's script |
| State | `/opt/data/state/hn-brief-email.last-sent.json` — never sends a date twice |
| Log | `/opt/data/logs/hn-brief-email.log` |
| Cache | `/opt/data/cache/hn-brief-email/<date>.txt` and `.html` |
| Delivery | silent on success/skip (`deliver: local`); a send failure exits 2 → Signal |

Skip rules (silent, exit 0): briefing date != today in America/New_York (the
07:45 run exits quietly when the pipeline is late and the 08:15/09:15 runs pick
it up, then nothing until the next day), `quality.digestValid` false, or the
date already sent.

Credentials: `SMTP_HOST`, `SMTP_PORT` (587, STARTTLS), `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_FROM` — or the `EMAIL_SMTP_HOST` / `EMAIL_ADDRESS` /
`EMAIL_PASSWORD` naming Hermes' email platform uses (both resolve). Sources, in
order: `/opt/data/secrets/mail.env`, `/opt/data/.env` (the container's master
env), `/opt/data/secrets/hermes.env`, and only then the process environment as a
fallback — **files win**, because the process env is a snapshot from gateway
start and a stale value there must not shadow the corrected file (run
`scripts/smtp-diagnose.py` to see which source each key came from). Commented-out
lines are ignored. The password is used only for `smtplib.login()`; it is never
printed, logged, cached or written anywhere. With no credentials the job logs
`NOT SENT … SMTP not configured` (naming every location it checked) and exits 0,
silent.

## Answering rules

1. **Cite every claim**: story title + article URL. Add the HN discussion link
   when the question is about the HN reaction. Never cite a title without its
   link.
2. **Rank is rank order** in `stories[]` — index 1 is the top story of that day.
3. **"This week"** = union of `archive.json` dates within the last 7 days;
   `search --days 7` does that. Say which dates you covered.
4. **Staleness check**: after 08:00 America/New_York, if `latest.json.date` is
   not today's NY date, say: "today's run may have failed (latest is <date>)".
   Do not present a stale day as today. The reader prints this warning itself.
5. **Digest vs stories**: `digest` is one written essay over the day;
   `summary`/`discussion_summary` are per-story. Don't attribute an essay claim
   to a specific story unless that story's summary supports it.
6. **Missing data**: if the date isn't in the dataset, say so. Never invent a
   story, URL, points value, or id.

## Pitfalls

- `runs/` is not the product — ignore it.
- The mount is read-only: writes fail. Generated artifacts go under
  `/opt/data/cache/`.
- `date` in the JSON is the authoritative label, not the file's mtime.
- `daily/YYYY/MM/DD.md` mirrors the JSON; use it only when you want
  pre-rendered Markdown, never as a parse source.
- The cron entry point must be a **real file** inside `HERMES_HOME/scripts/`
  (`/opt/data/scripts/`): a symlink resolving outside that directory is
  rejected by the cron validator as path traversal. Hence the shim; the
  implementation lives in `scripts/` of this skill so it ships with the skill.
- **Gmail closes the socket right after a 535**, so `smtplib` reports
  `SMTPServerDisconnected` rather than an auth failure. The job translates that
  into "connection closed during AUTH — usually a rejected login" and logs it;
  run `scripts/smtp-diagnose.py` to read Gmail's actual response code. A Gmail
  app password is 16 lowercase letters — a short or placeholder value in
  `SMTP_PASSWORD` produces exactly this 535.
- The scripts here are canonical; the repo copy under
  `research/hn-brief-dataset/` is what the nightly rebuild restores.
- **Deployment trap:** the nightly sync hard-resets the repo's `main` to
  `origin/main`, so a local commit of new skill files is discarded before the
  sync looks for changes. New skills must be committed to a *pushed* feature
  branch (upstream PR) **and** left as untracked files in the repo working tree —
  the rebuild copies the working tree, and the sync stages untracked files onto
  its `update/local-<date>` branch.

## References

- `references/validation-spec.md` — what a correct answer / email must contain.
- `references/scheduled-email-job.md` — the general recipe behind the job above
  (cron entry-point rule, credential lookup, dedupe, verify-without-sending).
  Reuse it for any other report that has to be emailed on a schedule.
