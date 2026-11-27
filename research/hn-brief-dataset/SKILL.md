---
name: hn-brief-dataset
description: "Query the local HN Brief dataset: today, history, search."
version: 1.3.0
author: Hermes Agent 01
license: MIT
metadata:
  hermes:
    tags: [hacker-news, hn, dataset, daily, weekly, monthly, research, local-data, email, discord]
    related_skills: [hn-brief-digest, unified-digest-themes, grounded-citations]
---

# HN Brief Dataset (local, read-only) + daily/weekly/monthly delivery

Answer HN questions from the machine-readable dataset a pipeline on lunarBeacon
writes daily at ~07:13 America/New_York, and ship the same briefing to email, the
Discord Daily Channel (#hacker-news) **and the Signal `Daily Notices` group** at
07:45. Each story carries its own discussion context: the model's
`discussion_summary` plus the verbatim `topComments` the pipeline publishes.
No scraping, no browser, no guessing.

## Data root

`/opt/shared_space/hn-brief-data` (read-only mount). Never write to it.

```
latest.json            {date, runId, path}      ← always start here
archive.json           [{date, path, runId, storyCount}, ...] newest first
daily/YYYY/MM/DD.json  full day: date, generatedAt, runId, source, model,
                       digest (long essay), quality{storyFailures, storyCount,
                       digestValid}, stories[] in rank order
daily/YYYY/MM/DD.md    ready-made Markdown of the same day
runs/                  raw debugging traces — IGNORE, not the product
```

Story fields: `id`, `title`, `url`, `points`, `num_comments`, `postType`,
`summary` (the article), `discussion_summary` (the HN comments), `topComments`
(live on every story since 2026-11-25: up to 10 verbatim comments, best first, as
`{id, author, text, score, depth, url}`, where `url` is the comment's HN permalink,
`text` is plain text with entities decoded, and `score` is a ranking score
(0–20ish), **not** HN points — never print it as "points"), and `articleSource`
(live since 2026-11-26: how the pipeline got the article before summarizing it).

`articleSource` values and what they mean for the reader:

| value | meaning | how to present it |
|---|---|---|
| `fetched` | the article was fetched and summarized | normal |
| `fetch_failed` | the fetch failed; the summary leans on link metadata | flag it — the article was not read |
| `self_post` | an HN text post (Ask/Tell HN); there is no article | flag it — the URL is the HN item itself |
| `pdf_skipped` | a PDF the pipeline did not parse | flag it — the paper was not read |

Never present a non-`fetched` summary as if the article had been read. The
scripts add a short `[…]` marker in that case; do the same in prose.

Both fields are newer than the dataset and arrived **without a `schemaVersion`
bump** (it is still 1), so read the JSON before assuming a shape: a day before
2026-11-25 has no `topComments`, a day before 2026-11-26 has no
`articleSource`. Missing means "wasn't published that day" — say so, never
synthesise comments or provenance to fill the gap.

HN discussion link: `https://news.ycombinator.com/item?id=<id>`.

## Scripts (shipped with this skill)

`scripts/hn-brief-data.py` — reader; use it instead of hand-parsing (~60 KB/day):

```bash
python3 <skill>/scripts/hn-brief-data.py latest          # today, all 20 stories
python3 <skill>/scripts/hn-brief-data.py top 5 [--date 2026-11-18]
python3 <skill>/scripts/hn-brief-data.py search "rust" --days 7 --snippets
python3 <skill>/scripts/hn-brief-data.py day 2026-11-21 --full [--comments 3]
python3 <skill>/scripts/hn-brief-data.py digest [--date D]
python3 <skill>/scripts/hn-brief-data.py days            # published dates
```

Any subcommand accepts `--json`. Prefer the scripts over reading JSON inline:
the digest alone is ~19 KB, easy to truncate or mis-parse by hand.

`scripts/hn-brief-email.py` — the DAILY delivery: deterministic, no LLM. Sends
the day's briefing to email, posts it to the Discord Daily Channel, and posts a
phone-sized version to Signal `Daily Notices` — each target with its own
already-sent record. Every story renders, in order: both links, `summary` (the
article), `discussion_summary` (the thread), then up to `--comments` verbatim top
comments (author, ranking score, comment link). The article summary line is not
optional garnish — without it the briefing is a link list, so it defaults on for
every target (`--summary-chars`, Signal `--signal-summary-chars`).
Stories whose `articleSource` is not `fetched` carry a short
`[article fetch failed …]` marker so the summary is never passed off as the
article. The briefing got materially longer when `topComments` went live
(2026-11-25: 30 Discord messages / 16 Signal messages in one day), so Signal has
its own tighter comment budget — `--signal-comments` (default 1) and
`--signal-comment-chars` (default 140).
Flags: `--targets email,discord,signal` (default), `--dry-run`, `--force`,
`--allow-stale` (send a briefing whose date isn't today — manual re-post or a
transport test), `--to`, `--channel`, `--signal-target`, `--comments`,
`--comment-chars`, `--discussion-chars`, `--signal-discussion-chars`,
`--signal-comments`, `--signal-comment-chars`, `--signal-digest-chars`.

`scripts/hn-brief-period.py` — builds the compact weekly/monthly corpus (the
last N published days: top headlines + a bounded digest excerpt). Stories whose
`articleSource` is not `fetched` are tagged `(src: … — article not read)` so the
aggregator describes them from the headline and digest only. Flags:
`--days N`, `--label weekly|monthly`, `--headlines`, `--digest-chars`, `--json`.

`scripts/smtp-diagnose.py` — transport triage: credential sources, banner, EHLO
capabilities, STARTTLS certificate, raw AUTH exchange with the server's own
response codes. Never prints the password. Run it first on any send failure.

## Delivery jobs

The daily script is the single entry point for the Daily Channel's content; the
weekly/monthly aggregators summarize N days of the dataset with the local model.
Full job/transport detail: `references/channel-delivery.md`.

| Job | Schedule (UTC) | Deliver | Mode |
|---|---|---|---|
| `hn-brief-email` + 2 retries | 12:45 / 13:15 / 14:15 | email, Discord `#hacker-news`, Signal `Daily Notices` | deterministic script |
| `hn-brief-weekly-aggregate` | Sun 20:00 | Discord `#hacker-news-weekly` | local LLM over 7-day corpus |
| `hn-brief-monthly-aggregate` | 1st 18:00 | Discord `#hacker-news-monthly` | local LLM over 30-day corpus |

The jobs pass no `--targets`, so the script's own default is the single switch for
where the briefing goes.

Skip rules (silent, exit 0): briefing date != today in America/New_York (the
07:45 run exits quietly when the pipeline is late and the 08:15/09:15 retries
pick it up), `quality.digestValid` false. A real transport failure exits 2, which
raises a cron failure alert — every HN job carries `failure_deliver: signal`, so
that alert lands in the Signal main channel (the DM), never in a digest channel.

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

- **Additive dataset fields arrive unversioned.** `topComments` (2026-11-25) and
  `articleSource` (2026-11-26) both landed with `schemaVersion` still 1. Dump the
  key set of a fresh day before trusting the field list above; the scripts tolerate
  missing fields, so older days still render without them.
- `runs/` is not the product — ignore it.
- The mount is read-only: writes fail. Generated artifacts go under
  `/opt/data/cache/`.
- `date` in the JSON is the authoritative label, not the file's mtime.
- The dataset is young (started ~2026-11-15): a 30-day window may cover far
  fewer than 30 published dates. Report the real window; never pad it.
- The cron entry point must be a **real file** inside `HERMES_HOME/scripts/`
  (`/opt/data/scripts/`): a symlink resolving outside that directory is
  rejected by the cron validator as path traversal. Hence the shims; the
  implementations live in `scripts/` of this skill so they ship with it.
- Discord caps a message at 2000 chars. `hn-brief-email.py` chunks its own
  posts; a cron job's *response* is chunked by the gateway adapter — so both
  paths survive long digests.
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

- `references/channel-delivery.md` — the daily/weekly/monthly jobs, targets,
  chunking, credential lookup, dedupe state, and the local-model provider.
- `references/validation-spec.md` — what a correct answer / delivery must contain.
