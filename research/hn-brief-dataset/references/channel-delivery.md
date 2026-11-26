# HN Brief delivery: Daily Channel + weekly/monthly aggregators

Companion to `SKILL.md`. Everything here is deterministic except the two
aggregator jobs, which summarize with the local model.

## Discord targets (NJL's server)

| Channel | id | Fed by |
|---|---|---|
| `#hacker-news` (the Daily Channel) | `1503214829509410887` | `hn-brief-email.py` (every day) |
| `#hacker-news-weekly` | `1507971737055264831` | `hn-brief-weekly-aggregate` |
| `#hacker-news-monthly` | `1507971842374111363` | `hn-brief-monthly-aggregate` |

## Daily: `hn-brief-email.py` (email + Daily Channel + Signal Daily Notices)

| Piece | Value |
|---|---|
| Targets | `email,discord,signal` (default; override with `--targets`, `HN_BRIEF_TARGETS`) |
| Per-story blocks | every story renders with its `discussion_summary` and, when the day publishes them, up to 2 verbatim `topComments` (`• author (score): text  <comment url>`) |
| Email | `HN Brief — <date>`; header → 20 stories (points, comments, article URL, HN link, discussion clip, top comments) → `DIGEST` → full digest; multipart plain + HTML |
| Discord | the same full briefing, chunked to Discord's 2000-char cap (one message per chunk, `(i/n)` suffix) |
| Signal | a **phone-sized render of the same day**, chunked at 1600 chars (`[i/n]` prefix): shorter discussion clips (300 vs 450 chars) and a 1200-char digest head plus a pointer to the full essay. Sent with `hermes send -t signal:Daily Notices` — no token of its own, the group name resolves through the gateway's Signal config |
| Cron | three runs, `timezone: America/New_York` — 07:45 (main), 08:15 and 09:15 (retries); `deliver: local` (the script posts Discord and Signal itself) |
| Entry point | `HERMES_HOME/scripts/hn-brief-email.py` (real-file shim) → this skill's script |
| State | `/opt/data/state/hn-brief-email.last-sent.json`, `hn-brief-discord.last-sent.json`, `hn-brief-signal.last-sent.json` — one per target, so a failure on one never suppresses the others |
| Log | `/opt/data/logs/hn-brief-email.log` |
| Cache | `/opt/data/cache/hn-brief-email/<date>.txt`, `.html`, `.signal.txt` |
| Exit | 0 on success/skip (silent); 2 on a real transport failure so `hermes cron list` shows `last_status=error` |

The briefing is input-dominated by the discussion text: the full render is ~38 KB
(24 Discord messages) and the Signal render ~12 KB (9 messages). `--dry-run`
prints both chunk counts before anything is sent.

Skip rules (silent, exit 0): briefing date != today in America/New_York (the
07:45 run exits quietly when the pipeline is late and the 08:15/09:15 runs pick
it up), `quality.digestValid` false. A real transport failure exits 2, which
raises a cron failure alert — routed to the Signal main channel (see Failure
routing below), not into any digest channel.

## Failure routing

Every HN job carries `failure_deliver: signal` — failure alerts go to the Signal
**main channel** (the DM, `SIGNAL_HOME_CHANNEL`), never to the Daily Notices
group and never into a Discord digest channel. The daily jobs stay
`deliver: local` so their *success* output is silent (the script posts to Discord
itself), while a non-zero exit still raises the failure alert. The aggregators
deliver their digest to Discord and route only failures to Signal.

Credentials, first hit wins, **files before the process env** (the process env is
a snapshot from gateway start; a stale value there must not shadow the file):

1. `/opt/data/secrets/mail.env`
2. `/opt/data/.env` (the container's master env)
3. `/opt/data/secrets/hermes.env`
4. process environment (fallback only)

Email keys: `SMTP_HOST`, `SMTP_PORT` (587, STARTTLS), `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_FROM` — or the `EMAIL_SMTP_HOST` / `EMAIL_ADDRESS` /
`EMAIL_PASSWORD` naming Hermes' email platform uses. Discord key:
`DISCORD_BOT_TOKEN`. The password is used only for `smtplib.login()` and the
token only for the `Authorization: Bot` header — neither is printed, logged,
cached or written anywhere.

## Weekly / monthly: local-LLM aggregators

Both are cron jobs in agent mode: a prep script's stdout is injected into the
prompt as the corpus, the model writes the digest, and the job's response is
delivered to the Discord channel (the gateway chunks long responses).

| Job | id | Schedule (UTC) | Deliver |
|---|---|---|---|
| `hn-brief-weekly-aggregate` | `70054ac63947` | `0 20 * * 0` | `discord:1507971737055264831` |
| `hn-brief-monthly-aggregate` | `a62c189a80a5` | `0 18 1 * *` | `discord:1507971842374111363` |

| Piece | Weekly | Monthly |
|---|---|---|
| Prep shim (real file in `HERMES_HOME/scripts/`) | `hn-brief-weekly-prep.py` | `hn-brief-monthly-prep.py` |
| Corpus | last 7 published days, 20 headlines/day, 3000-char digest excerpt, each story with its own `article:` + `hn:` URL | last 30 published days, 12 headlines/day, 1500-char excerpt, same URL contract |
| Skills | `unified-digest-themes`, `hn-brief-dataset` | same |
| Model / provider | `qwen3.8-27b-instruct-mtp-d3-ctx131k-no-backend-sampling` / `ollama-qwen3.6:27b` (local, `http://host.containers.internal:11434/v1`) | same |
| Toolsets | `["file"]` only (read_file/write_file — never terminal) | same |
| Own-output cache | `/opt/data/cache/hn-brief/weekly/<YYYY-Www>.md` (path printed as `save_to:` in the corpus) | `/opt/data/cache/hn-brief/monthly/<YYYY-MM>.md` |
| Wrapping | `wrap_response: false` — delivered raw, no cron header/footer | same |

Notes that cost time if forgotten:

- The local model is slow by design; these are infrequent jobs and a run may
  take tens of minutes. Do not shorten the corpus to "speed it up" unless output
  quality is actually suffering.
- **Never give a cron agent the terminal tool for writing output.** A scheduled
  run has no user present, so approval-gated commands (heredocs, `python -c`)
  come back `BLOCKED`. The model retries a blocked command instead of moving on,
  burns the whole 60-tool-call budget, and delivers an *error message to the
  channel* — status still reads `ok`/`delivered`, so only reading the output
  catches it. Save with `write_file` (read first if it already exists), give the
  job `enabled_toolsets: ["file"]`, and state in the prompt: never use the
  terminal, never retry a failed tool call, return the digest regardless. A
  17K-char monthly digest was produced and cached while the run still failed to
  deliver — always verify the channel, not just `last_status`.
- The prompt is the contract. Cron agents follow the **prompt**, not the whole
  attached skill, so every mandatory step (format, citation rule, no Jargon
  section, `save_to` write) is restated in the prompt itself.
- Pick the instruct model with an explicit large context. `qwen3.8-27b` (no
  `-instruct`) is a thinking model — it emits `reasoning_content` and returns
  nothing usable for a digest. And on this endpoint use the `ctx131k` variant:
  Hermes resolves 131,072 tokens for the model from its catalog, but the local
  server's own window is the binding limit, and the full agent request (skills +
  ~23 K tokens of deferred tool schemas + an ~11 K-token corpus) exceeded it
  while a bare 11 K-token call succeeded. Restricting `enabled_toolsets` to
  `["terminal"]` plus the `ctx131k` variant fixes it.
- Do not silently shrink the corpus to dodge a context error; measure first. A
  44 KB corpus (~11 K tokens) round-trips fine as a direct call.
- Jargon is **not** emitted by these jobs. Presentation is owned by the
  `jargon-notify` job; these digests are content only.

## Verifying without waiting

```bash
S=/opt/data/skills/research/hn-brief-dataset/scripts
python3 $S/hn-brief-email.py --dry-run          # render + count Discord and Signal chunks
python3 $S/hn-brief-email.py --targets discord  # post only the Daily Channel
python3 $S/hn-brief-email.py --targets signal --allow-stale   # re-post / transport test
python3 $S/hn-brief-period.py --days 7 | head   # inspect the weekly corpus
```

`--allow-stale` bypasses the "briefing date must be today" skip, which is the only
way to exercise the Signal path (or re-post a day) outside the 07:45–09:15 window.
It logs a WARNING line every time it is used.

Read the channel back to confirm a post really landed (bot token from `.env`):

```bash
curl -s -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
  "https://discord.com/api/v10/channels/1503214829509410887/messages?limit=5"
```

## History

- The pre-Aug-2026 daily job scraped `hn-brief.com` with a browser and posted a
  themed digest at 22:00 UTC. It was paused 2026-08-24 ("stop all hacker news
  jobs until I fix the underlying code") and superseded by this dataset pipeline.
- The four legacy jobs (`hn-brief-daily-digest`, `-weekly-digest`,
  `-monthly-digest`, `-popularity-tracker`) were REMOVED on 2026-11-24. They
  read the old `/opt/data/cache/hn-brief/YYYY/MM/DD/` cache, not this dataset.
