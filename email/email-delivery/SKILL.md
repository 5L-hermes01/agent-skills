---
name: email-delivery
description: "Send mail from the host: SMTP scripts, Hermes transport."
version: 1.0.0
author: Hermes Agent 01
license: MIT
metadata:
  hermes:
    tags: [email, smtp, gmail, delivery, cron, transport, credentials]
    related_skills: [himalaya, email-inbox-triage, hn-brief-dataset]
---

# Outbound email from this host

## When to Use

Load this when anything has to leave the machine as mail: a scheduled digest or
report, a notification, an ad-hoc send, or wiring mail up as a Hermes transport —
including "the send failed, why" on any of those. For reading or triaging
inbound mail, use `email-inbox-triage` instead.

## Pick the transport

| Need | Path |
|---|---|
| Scheduled/structured content (own subject, multipart, exact body) | Python stdlib `smtplib` + `email.message` in a deterministic script — full control, no gateway |
| One-off mail from a shell/cron line | `scripts/send-mail.py --to <addr> --subject <s> --body <t>` (`--body-file`, `--html`, `--attach`, `--dry-run`) — stdlib, no gateway, works in send-only mode |
| Let people mail the agent and get thread replies | Hermes email platform: `EMAIL_*` env vars + `platforms.email.enabled true` + gateway restart |

`hermes send -t email:<address>` is gated on `platforms.email.enabled`: with it
false (this host) the CLI answers `Platform 'email' is not configured`. The
platform has **no send-only switch** — enabling it always starts the IMAP
poller — so route ad-hoc sends through `scripts/send-mail.py` instead.

## Host state (as configured)

- **Mode: send-only.** `platforms.email.enabled = false` is deliberate — no IMAP
  poller, no inbound agent channel. `hermes send -t email:<address>` still works
  (standalone sender, no gateway needed). Do not flip `enabled` to true without
  asking: the mailbox is the shared automatednotes inbox that MsgVault and the
  host notifiers read, and the adapter marks all existing mail as seen at startup.
- Credentials live in `/opt/data/.env` (the master env): `SMTP_HOST`, `SMTP_PORT`,
  `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` (used by the briefing script) and
  `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `EMAIL_IMAP_HOST`, `EMAIL_SMTP_HOST` plus
  `EMAIL_ALLOWED_USERS=nick.lange@gmail.com`, `EMAIL_HOME_ADDRESS=nick.lange@gmail.com`,
  `EMAIL_AUTHSERV_ID=mx.google.com`, `EMAIL_POLL_INTERVAL=60` (used by the Hermes
  platform). The same app password sits under both `SMTP_PASSWORD` and
  `EMAIL_PASSWORD` — **rotate them together**, or collapse to one pair (the
  briefing script accepts either name).
- The HN Brief daily job uses the stdlib script, not the Hermes transport: cron
  `bc46646a69cc` 07:45 America/New_York plus retries `1d58ad250ab2` 08:15 and
  `0742eda0e9a9` 09:15; state `/opt/data/state/hn-brief-email.last-sent.json`;
  log `/opt/data/logs/hn-brief-email.log`.

## Credentials

Sources, in this order: `/opt/data/secrets/mail.env`, `/opt/data/.env` (the
master env the gateway loads, `$HERMES_HOME/.env` in this deployment),
`/opt/data/secrets/hermes.env` (= `$HERMES_HOME/.hermes/.env`), then the process
environment as a fallback. Accept both namings: `SMTP_HOST/PORT/USER/PASSWORD/FROM`
and `EMAIL_SMTP_HOST/EMAIL_SMTP_PORT/EMAIL_ADDRESS/EMAIL_PASSWORD`.

- **Read the files before the process environment.** The process env is a
  snapshot taken when the gateway started, so a value that was a placeholder at
  boot keeps shadowing the corrected file and every send fails with an auth
  error that looks like a wrong password. Files win; a restart refreshes the env.
- A Gmail app password is 16 lowercase letters. Check the shape (length, no
  spaces/quotes/CR) before blaming the transport or the network.
- Never print, log, cache or echo the password — pass it straight to
  `smtplib.login()`, keep the env file `0600`, and make probes report lengths and
  source filenames only.
- Prefer one key name per secret. When two consumers force two names
  (`SMTP_PASSWORD` and `EMAIL_PASSWORD`), say so to the user: both must rotate
  together.

## Sending with stdlib

- STARTTLS on 587; implicit TLS only when the port is 465. Build the message as
  `EmailMessage` → `set_content(plain)` → `add_alternative(html, subtype="html")`
  so clients that strip HTML still read it; keep the plain part readable at
  phone width.
- **Gmail closes the socket immediately after a 535**, so `smtplib` raises
  `SMTPServerDisconnected` rather than `SMTPAuthenticationError`. Translate that
  to "connection closed during AUTH — usually a rejected login" instead of
  reporting a network fault, and confirm with `scripts/smtp-probe.py`.
- A `250` means accepted, not delivered. Verify with `scripts/verify-sent.py`,
  which reads the account's Sent folder over IMAP — that is the evidence.
- Treat missing credentials as a logged no-op (`exit 0`, one log line naming
  every location checked) and only a real send failure as non-zero, or the job
  fires a failure notice every day until someone provisions the secret.

## Scheduling delivery

- Hermes cron `--script` must be a **real file inside `$HERMES_HOME/scripts/`**
  (`/opt/data/scripts/`): a symlink whose target resolves outside that directory
  is rejected as path traversal. Keep the implementation with its skill and add a
  small shim in the scripts dir that `runpy.run_path`s it.
- Make the job idempotent: record the sent date in a state file, skip when it
  matches, and keep the state write atomic (temp file + `replace`) so a crash
  cannot double-send or lose the record.
- Schedule in the recipient's timezone with cron `--timezone` (wall-clock 07:45
  must stay 07:45 across DST) and add retry runs when an upstream pipeline may
  finish late. Skips stay silent; only failures alert (`--deliver local`,
  `--failure-deliver signal`).

## Turning on the gateway channel

- Enabling the platform points an IMAP poller at a real mailbox: at startup it
  marks all existing messages **as seen**, so mail other tooling reads (archivers,
  host notifiers) disappears from their unread view. Do not enable it on a shared
  notification inbox without telling the user; a dedicated agent mailbox is the
  clean answer.
- Set `EMAIL_ALLOWED_USERS` to the smallest set (unknown senders are otherwise
  ignored), `EMAIL_HOME_ADDRESS` as the cron delivery target, and
  `EMAIL_AUTHSERV_ID` to the exact authserv-id your receiving MTA stamps on its
  topmost `Authentication-Results` header (Gmail: `mx.google.com`) — without it
  mail from admitted senders is dropped.
- `hermes send -t email:<addr>` works with no gateway; only the inbound channel
  needs a restart. Never restart the gateway without the user's approval, and say
  plainly that the config is inert until then.

## Scripts

- `scripts/send-mail.py` — general one-shot sender: `--to` (repeatable),
  `--subject`, `--body|--body-file|stdin`, `--html`, `--attach`, `--from`,
  `--dry-run` (prints recipients, sizes and which file each credential came from,
  without connecting). Exit 2 on any real failure, with the reason on stderr.
  Also linked as `/opt/data/scripts/send-mail.py` for shell one-liners.
- `scripts/smtp-probe.py` — transport + raw AUTH diagnostics; prints the
  credential source of each key and the server's real response code, never the
  password.
- `scripts/verify-sent.py` — IMAP Sent-folder verification for a subject string.

A job-wired variant of the probe (reads the digest job's own credential loader)
lives in the `hn-brief-dataset` skill as `scripts/smtp-diagnose.py`.
