#!/usr/bin/env python3
"""HN Brief daily email — sends the day's briefing over SMTP. Deterministic, no LLM.

Data:  /opt/shared_space/hn-brief-data (latest.json -> daily/YYYY/MM/DD.json)
Send:  SMTP, STARTTLS, credentials from the environment or the secret store.
State: /opt/data/state/hn-brief-email.last-sent.json  (never sends a date twice)
Log:   /opt/data/logs/hn-brief-email.log

Exit without sending when:
  * latest.json's date is not today in America/New_York (the 07:45 run exits
    quietly and the 08:15 / 09:15 retries pick the briefing up), or
  * quality.digestValid is false, or
  * this date was already sent.

Credentials, first hit wins:
  1. process environment: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
     (EMAIL_SMTP_HOST / EMAIL_ADDRESS / EMAIL_PASSWORD also accepted — that is
     the naming Hermes' email platform template uses)
  2. /opt/data/secrets/mail.env            (KEY=VALUE lines)
  3. /opt/data/.env                        (master env for this container)
  4. /opt/data/secrets/hermes.env
Commented-out lines are ignored. SMTP_PASSWORD is only ever read into memory for
smtplib.login() — it is never echoed, logged, cached, or written to any file.

Usage
-----
  hn-brief-email.py --dry-run          # render only, no send
  hn-brief-email.py --force            # ignore the already-sent record
  hn-brief-email.py --to someone@x.com --dry-run
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_ROOT = Path("/opt/shared_space/hn-brief-data")
CACHE_DIR = Path("/opt/data/cache/hn-brief-email")
LOG = Path("/opt/data/logs/hn-brief-email.log")
STATE = Path("/opt/data/state/hn-brief-email.last-sent.json")
CRED_SOURCES = (
    Path("/opt/data/secrets/mail.env"),
    Path("/opt/data/.env"),
    Path("/opt/data/secrets/hermes.env"),
)
CRED_SOURCE_OF: dict[str, str] = {}  # key -> where its value came from (never the value)
NY = ZoneInfo("America/New_York")
DEFAULT_TO = "nick.lange@gmail.com"
MAX_HEADLINES = 20
# canonical key -> accepted names in priority order (SMTP_* first, then the
# EMAIL_* naming Hermes' email platform template ships with)
KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "SMTP_HOST": ("SMTP_HOST", "EMAIL_SMTP_HOST"),
    "SMTP_PORT": ("SMTP_PORT", "EMAIL_SMTP_PORT"),
    "SMTP_USER": ("SMTP_USER", "EMAIL_ADDRESS", "EMAIL_USER"),
    "SMTP_PASSWORD": ("SMTP_PASSWORD", "EMAIL_PASSWORD"),
    "SMTP_FROM": ("SMTP_FROM", "EMAIL_FROM", "EMAIL_ADDRESS", "EMAIL_HOME_ADDRESS"),
}


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(NY).strftime("%Y-%m-%d %H:%M:%S %Z")
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {msg}\n")


def hn_url(story: dict) -> str:
    return f"https://news.ycombinator.com/item?id={story['id']}"


# ── credentials ──────────────────────────────────────────────────────────────

def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def smtp_config() -> dict[str, str]:
    """Resolve SMTP settings from the env/secret files, then the process env.

    Accepts SMTP_* names and the EMAIL_* names Hermes' email-platform template
    uses (see KEY_ALIASES).

    **File first, process env last.** The files are what the operator edits; the
    process environment is a snapshot taken when the gateway started, so a stale
    value there (e.g. an old placeholder pasted before the real app password)
    must not shadow the corrected file. Values are never logged; the source file
    of each key is recorded in CRED_SOURCE_OF for diagnostics.
    """
    raw: dict[str, str] = {}
    for path in CRED_SOURCES:
        for key, val in parse_env_file(path).items():
            if val and key not in raw:
                raw[key] = val
                CRED_SOURCE_OF[key] = str(path)
    for key, val in os.environ.items():  # fallback only
        if val and key not in raw:
            raw[key] = val
            CRED_SOURCE_OF[key] = "process env"
    cfg: dict[str, str] = {}
    for canon, names in KEY_ALIASES.items():
        for name in names:
            if raw.get(name):
                cfg[canon] = raw[name]
                CRED_SOURCE_OF[canon] = CRED_SOURCE_OF.get(name, "?")
                break
    return cfg


# ── rendering ────────────────────────────────────────────────────────────────

def build_plain(day: dict) -> str:
    stories = day["stories"][:MAX_HEADLINES]
    out = [
        f"HN Brief — {day['date']}",
        f"{len(stories)} stories · generated {day.get('generatedAt', '?')} · run {day.get('runId', '?')}",
        "",
        "HEADLINES",
        "",
    ]
    for i, s in enumerate(stories, 1):
        out.append(f"{i}. {s['title']}  ({s['points']} points, {s.get('num_comments', 0)} comments)")
        out.append(f"   Article: {s['url']}")
        out.append(f"   Hacker News: {hn_url(s)}")
        out.append("")
    out += ["-" * 60, "", "DIGEST", "", (day.get("digest") or "(digest missing)").strip(), ""]
    return "\n".join(out)


def _linkify(text: str) -> str:
    escaped = html_mod.escape(text)
    return re.sub(r"(https?://[^\s<>\"')]+)",
                  r'<a href="\1">\1</a>', escaped)


def build_html(day: dict) -> str:
    stories = day["stories"][:MAX_HEADLINES]
    rows = []
    for s in stories:
        rows.append(
            '<li><a href="{url}">{title}</a> — {pts} points, {cmt} comments '
            '· <a href="{hn}">HN discussion</a></li>'.format(
                url=html_mod.escape(s["url"], quote=True),
                title=html_mod.escape(s["title"]),
                pts=s["points"],
                cmt=s.get("num_comments", 0),
                hn=hn_url(s),
            )
        )
    digest_blocks = [
        f"<p>{_linkify(block.strip())}</p>"
        for block in re.split(r"\n\s*\n", (day.get("digest") or "").strip())
        if block.strip()
    ]
    return (
        '<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'max-width:760px;line-height:1.5;color:#111">'
        f"<h2>HN Brief — {html_mod.escape(day['date'])}</h2>"
        f'<p style="color:#666;margin-top:-8px">{len(stories)} stories · generated '
        f"{html_mod.escape(str(day.get('generatedAt', '?')))} · run "
        f"{html_mod.escape(str(day.get('runId', '?')))}</p>"
        "<h3>Headlines</h3><ol>"
        + "".join(rows)
        + "</ol><hr><h3>Digest</h3>"
        + "".join(digest_blocks)
        + "</body></html>"
    )


# ── transport ────────────────────────────────────────────────────────────────

def send_smtp(cfg: dict[str, str], to: str, subject: str, plain: str, html_body: str) -> str:
    host = cfg["SMTP_HOST"]
    port = int(cfg.get("SMTP_PORT") or 587)
    user = cfg["SMTP_USER"]
    sender = cfg.get("SMTP_FROM") or user
    msg = EmailMessage()
    msg["From"] = formataddr(("HN Brief", sender))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="hn-brief.local")
    msg.set_content(plain)
    msg.add_alternative(html_body, subtype="html")
    context = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=60, context=context) as smtp:
                smtp.login(user, cfg["SMTP_PASSWORD"])
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=60) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(user, cfg["SMTP_PASSWORD"])
                smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError(
            f"login rejected by {host}: {exc.smtp_code} {exc.smtp_error.decode(errors='ignore') if isinstance(exc.smtp_error, bytes) else exc.smtp_error}"
        ) from exc
    except smtplib.SMTPServerDisconnected as exc:
        # Gmail closes the socket immediately after a 535, so smtplib reports a
        # disconnect instead of the auth failure. Say what that usually means.
        raise RuntimeError(
            f"connection closed during AUTH on {host}:{port} — usually a rejected "
            f"login (bad/revoked app password); run scripts/smtp-diagnose.py to read "
            f"the server's real response code"
        ) from exc
    return f"{host}:{port} starttls as {sender}"


# ── state ────────────────────────────────────────────────────────────────────

def last_sent_date() -> str | None:
    if not STATE.exists():
        return None
    try:
        return json.loads(STATE.read_text(encoding="utf-8")).get("last_sent")
    except (json.JSONDecodeError, OSError):
        return None


def record_sent(date: str, to: str) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_sent": date, "sent_at": datetime.now(NY).isoformat(timespec="seconds"), "to": to}
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(STATE)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="HN Brief daily email over SMTP")
    ap.add_argument("--to", default=os.environ.get("HN_BRIEF_EMAIL_TO", DEFAULT_TO))
    ap.add_argument("--dry-run", action="store_true", help="render only, never send")
    ap.add_argument("--force", action="store_true", help="send even if already sent today")
    args = ap.parse_args()

    if not DATA_ROOT.exists():
        log(f"dataset root {DATA_ROOT} not mounted")
        return 2
    meta = json.loads((DATA_ROOT / "latest.json").read_text(encoding="utf-8"))
    day = json.loads((DATA_ROOT / meta["path"]).read_text(encoding="utf-8"))
    date = day["date"]
    today = datetime.now(NY).strftime("%Y-%m-%d")
    subject = f"HN Brief — {date}"

    if date != today:
        log(f"skip: briefing date {date} != today {today} in America/New_York (retry window covers 08:15/09:15)")
        return 0
    if not (day.get("quality") or {}).get("digestValid", False):
        log(f"skip: digestValid=false for {date}")
        return 0
    if last_sent_date() == date and not args.force:
        log(f"skip: {date} already sent")
        return 0

    plain = build_plain(day)
    html_body = build_html(day)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{date}.txt").write_text(f"To: {args.to}\nSubject: {subject}\n\n{plain}", encoding="utf-8")
    (CACHE_DIR / f"{date}.html").write_text(html_body, encoding="utf-8")

    if args.dry_run:
        print(f"rendered {CACHE_DIR / (date + '.txt')} ({len(plain)} chars plain, {len(html_body)} chars html)")
        return 0

    cfg = smtp_config()
    missing = [k for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD") if not cfg.get(k)]
    if missing:
        log(f"NOT SENT {date}: SMTP not configured (missing {', '.join(missing)}); "
            f"expected SMTP_* (or EMAIL_*) in the process env or one of "
            f"{', '.join(str(p) for p in CRED_SOURCES)}")
        return 0

    try:
        how = send_smtp(cfg, args.to, subject, plain, html_body)
    except Exception as exc:  # noqa: BLE001 — credentials never appear in these messages
        log(f"SEND FAILED {date} to {args.to}: {type(exc).__name__}: {exc}")
        print(f"HN Brief email NOT sent ({date}): {type(exc).__name__}: {exc}")
        return 2
    record_sent(date, args.to)
    log(f"sent {date} to {args.to} via {how} ({len(plain)} chars plain / {len(html_body)} chars html)")
    print(f"HN Brief — {date} sent to {args.to} via {how}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
