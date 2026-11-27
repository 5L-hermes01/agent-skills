#!/usr/bin/env python3
"""HN Brief daily delivery — the day's briefing to email AND the Daily Channel.

Deterministic, no LLM. One entry point, three independent targets, each with its
own already-sent record so a failure on one never suppresses the others.

Data:  /opt/shared_space/hn-brief-data (latest.json -> daily/YYYY/MM/DD.json)
Email: SMTP STARTTLS, credentials from the secret store / environment.
Slack: n/a
Discord: bot token REST post to the Daily Channel (#hacker-news), chunked at
         Discord's 2000-char message limit.
Signal: `hermes send -t signal:<group>` (Daily Notices), chunked smaller for a
        phone — and rendered tighter: shorter discussion clips, a digest head
        instead of the whole essay, because a notices group is not an archive.
State: /opt/data/state/hn-brief-email.last-sent.json
       /opt/data/state/hn-brief-discord.last-sent.json
       /opt/data/state/hn-brief-signal.last-sent.json
Log:   /opt/data/logs/hn-brief-email.log

Each story renders in rank order: title + points/comments, the article URL, the
HN discussion URL, `summary` (the model's summary OF THE ARTICLE — the part that
makes the briefing readable without opening anything), `discussion_summary` (the
model's summary of the HN thread), and, when the pipeline publishes it,
`topComments` — up to 10 verbatim comments, best first, as {id, author, text,
score, depth, url}. Nothing is invented: a day whose JSON has no `summary` or
`topComments` simply shows the fields it does have.

Delivery is SILENT on success/skip (the cron job runs with deliver: local) — the
script posts to Discord and Signal itself so nothing needs forwarding. A real
transport failure prints a line and exits 2 so `hermes cron list` shows
last_status=error.

Exit without sending when:
  * latest.json's date is not today in America/New_York (the 07:45 run exits
    quietly and the 08:15 / 09:15 retries pick the briefing up), or
  * quality.digestValid is false.

Email credentials, first hit wins:
  1. /opt/data/secrets/mail.env            (KEY=VALUE lines)
  2. /opt/data/.env                        (master env for this container)
  3. /opt/data/secrets/hermes.env
  4. process environment                   (fallback only)
Names: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
(the EMAIL_SMTP_HOST / EMAIL_ADDRESS / EMAIL_PASSWORD naming Hermes' email
platform template uses is also accepted). Commented-out lines are ignored.
SMTP_PASSWORD is only ever read into memory for smtplib.login() — never echoed,
logged, cached, or written to any file.

Usage
-----
  hn-brief-email.py --dry-run                      # render only, no send
  hn-brief-email.py --targets discord              # Daily Channel only
  hn-brief-email.py --targets email --force        # re-send the email
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
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_ROOT = Path("/opt/shared_space/hn-brief-data")
CACHE_DIR = Path("/opt/data/cache/hn-brief-email")
LOG = Path("/opt/data/logs/hn-brief-email.log")
STATE = Path("/opt/data/state/hn-brief-email.last-sent.json")
DISCORD_STATE = Path("/opt/data/state/hn-brief-discord.last-sent.json")
SIGNAL_STATE = Path("/opt/data/state/hn-brief-signal.last-sent.json")
CRED_SOURCES = (
    Path("/opt/data/secrets/mail.env"),
    Path("/opt/data/.env"),
    Path("/opt/data/secrets/hermes.env"),
)
CRED_SOURCE_OF: dict[str, str] = {}  # key -> where its value came from (never the value)
NY = ZoneInfo("America/New_York")
DEFAULT_TO = "nick.lange@gmail.com"
MAX_HEADLINES = 20
# The Daily Channel — Discord #hacker-news on NJL's server.
DEFAULT_DISCORD_CHANNEL = "1503214829509410887"
DISCORD_API = "https://discord.com/api/v10"
DISCORD_SAFE_LIMIT = 1900  # Discord hard-caps a message at 2000 chars
# The Daily Notices group on Signal — the same briefing, rendered for a phone.
DEFAULT_SIGNAL_TARGET = "signal:Daily Notices"
SIGNAL_SAFE_LIMIT = 1600  # below Signal's per-message ceiling, and short enough
#                           that one story block rarely straddles two messages
DEFAULT_SUMMARY_CHARS = 360       # per-story ARTICLE summary ("Summary:"), email + Discord
DEFAULT_SIGNAL_SUMMARY_CHARS = 240
DEFAULT_DISCUSSION_CHARS = 320    # per-story discussion summary, email + Discord
DEFAULT_SIGNAL_DISCUSSION_CHARS = 200
DEFAULT_SIGNAL_DIGEST_CHARS = 1200  # digest head only, with a pointer
DEFAULT_COMMENTS = 2             # verbatim top comments per story (0 = none)
DEFAULT_COMMENT_CHARS = 180
# A notices group is not an archive: one short comment per story is colour,
# two full ones made a 16-message flood the day topComments went live.
DEFAULT_SIGNAL_COMMENTS = 1
DEFAULT_SIGNAL_COMMENT_CHARS = 120
# `articleSource` (new 2026-11-26) says how the pipeline got the article before
# summarizing it. Anything but "fetched" means the summary leans on metadata,
# the HN post itself, or an unparsed PDF — say so instead of implying we read it.
PROVENANCE_NOTES = {
    "fetch_failed": "article fetch failed — summary is from the link, not the page",
    "self_post": "no article — summary is the HN post itself",
    "pdf_skipped": "PDF not parsed — summary is from the link, not the paper",
}
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


def provenance_note(story: dict) -> str:
    """Caveat for stories whose article was not actually read; '' when fetched."""
    return PROVENANCE_NOTES.get(str(story.get("articleSource") or ""), "")


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


def _resolved_env() -> dict[str, str]:
    """Secrets from files first, process env last (files win — see below).

    The process environment is a snapshot taken when the gateway started, so a
    stale value there (e.g. an old placeholder pasted before the real app
    password) must not shadow the corrected file. Values are never logged.
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
    return raw


def smtp_config() -> dict[str, str]:
    """Resolve SMTP settings from the env/secret files, then the process env."""
    raw = _resolved_env()
    cfg: dict[str, str] = {}
    for canon, names in KEY_ALIASES.items():
        for name in names:
            if raw.get(name):
                cfg[canon] = raw[name]
                CRED_SOURCE_OF[canon] = CRED_SOURCE_OF.get(name, "?")
                break
    return cfg


def discord_token() -> str | None:
    """Bot token for the Daily Channel; files win over the process env."""
    return _resolved_env().get("DISCORD_BOT_TOKEN") or None


# ── rendering ────────────────────────────────────────────────────────────────

def _clip(text: str, limit: int) -> str:
    """Collapse whitespace and trim to `limit` chars on a word boundary."""
    text = " ".join((text or "").split())
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut[limit // 2:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:—-") + "…"


def story_block(i: int, s: dict, *, summary_chars: int, discussion_chars: int,
                comments: int, comment_chars: int) -> list[str]:
    """One ranked story: title, both links, the article summary, the discussion
    summary, and the top comments.

    `summary` is the model's summary OF THE ARTICLE — the reason the briefing is
    readable without opening anything; it was missing from the render until
    2026-11-27, which left the briefing as a link list plus quarantine notes.
    `topComments` is whatever the pipeline published — {id, author, text, score,
    depth, url} per PR #4. Absent field means the day simply has no verbatim
    comments; nothing is synthesised to fill the gap.
    """
    out = [
        f"{i}. {s['title']}  ({s['points']} points, {s.get('num_comments', 0)} comments)",
        f"   Article: {s['url']}" + (f"  [{note}]" if (note := provenance_note(s)) else ""),
        f"   Hacker News: {hn_url(s)}",
    ]
    summary = _clip(s.get("summary") or "", summary_chars) if summary_chars else ""
    if summary:
        out.append(f"   Summary: {summary}")
    discussion = _clip(s.get("discussion_summary") or "", discussion_chars) if discussion_chars else ""
    if discussion:
        out.append(f"   Discussion: {discussion}")
    for c in (s.get("topComments") or [])[: max(comments, 0)]:
        who = c.get("author") or "?"
        score = c.get("score")
        line = f"   • {who}" + (f" · {score:g}" if isinstance(score, (int, float)) else "")
        body = _clip(c.get("text") or "", comment_chars)
        if body:
            line += f": {body}"
        if c.get("url"):
            line += f"  {c['url']}"
        out.append(line)
    out.append("")
    return out


def build_plain(day: dict, *, summary_chars: int = 0, discussion_chars: int = 0,
                comments: int = 0, comment_chars: int = DEFAULT_COMMENT_CHARS,
                digest_chars: int = 0, digest_note: str = "") -> str:
    """The briefing as plain text.

    Defaults reproduce the pre-comment briefing exactly; the daily run passes the
    per-target clip lengths so email/Discord carry the full briefing while Signal
    gets a phone-sized version of the same day.
    """
    stories = day["stories"][:MAX_HEADLINES]
    out = [
        f"HN Brief — {day['date']}",
        f"{len(stories)} stories · generated {day.get('generatedAt', '?')} · run {day.get('runId', '?')}",
        "",
        "HEADLINES",
        "",
    ]
    for i, s in enumerate(stories, 1):
        out += story_block(i, s, summary_chars=summary_chars, discussion_chars=discussion_chars,
                           comments=comments, comment_chars=comment_chars)
    digest = (day.get("digest") or "(digest missing)").strip()
    if digest_chars:
        digest = _clip(digest, digest_chars) + (digest_note or "")
    out += ["-" * 60, "", "DIGEST", "", digest, ""]
    return "\n".join(out)


def _linkify(text: str) -> str:
    escaped = html_mod.escape(text)
    return re.sub(r"(https?://[^\s<>\"')]+)",
                  r'<a href="\1">\1</a>', escaped)


def build_html(day: dict, *, summary_chars: int = 0, discussion_chars: int = 0,
               comments: int = 0, comment_chars: int = DEFAULT_COMMENT_CHARS) -> str:
    stories = day["stories"][:MAX_HEADLINES]
    rows = []
    for s in stories:
        block = [
            '<li><a href="{url}">{title}</a> — {pts} points, {cmt} comments '
            '· <a href="{hn}">HN discussion</a>{note}'.format(
                url=html_mod.escape(s["url"], quote=True),
                title=html_mod.escape(s["title"]),
                pts=s["points"],
                cmt=s.get("num_comments", 0),
                hn=hn_url(s),
                note=(f' <span style="color:#a00;font-size:0.9em">[{html_mod.escape(provenance_note(s))}]</span>'
                      if provenance_note(s) else ""),
            )
        ]
        summary = _clip(s.get("summary") or "", summary_chars) if summary_chars else ""
        if summary:
            block.append(f'<div style="margin:3px 0">{html_mod.escape(summary)}</div>')
        discussion = _clip(s.get("discussion_summary") or "", discussion_chars) if discussion_chars else ""
        if discussion:
            block.append(f'<div style="color:#333;margin:3px 0">{html_mod.escape(discussion)}</div>')
        for c in (s.get("topComments") or [])[: max(comments, 0)]:
            body = _clip(c.get("text") or "", comment_chars)
            if not body:
                continue
            who = html_mod.escape(str(c.get("author") or "?"))
            score = c.get("score")
            link = (f' <a href="{html_mod.escape(str(c["url"]), quote=True)}">comment</a>'
                    if c.get("url") else "")
            block.append(
                f'<div style="color:#555;font-size:0.94em;margin:0 0 3px 16px">— {who}'
                + (f" · {score:g}" if isinstance(score, (int, float)) else "")
                + f"{link}: {html_mod.escape(body)}</div>"
            )
        block.append("</li>")
        rows.append("".join(block))
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


# ── transport: email ─────────────────────────────────────────────────────────

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


# ── transport: Discord (the Daily Channel) ───────────────────────────────────

def split_for_discord(text: str, limit: int = DISCORD_SAFE_LIMIT) -> list[str]:
    """Split on line boundaries into chunks that fit Discord's 2000-char cap."""
    parts: list[str] = []
    cur = ""
    for line in text.split("\n"):
        while len(line) > limit:            # a single line longer than a message
            if cur:
                parts.append(cur.rstrip())
                cur = ""
            parts.append(line[:limit])
            line = line[limit:]
        if not cur:
            cur = line
        elif len(cur) + 1 + len(line) > limit:
            parts.append(cur.rstrip())
            cur = line
        else:
            cur += "\n" + line
    if cur.strip():
        parts.append(cur.rstrip())
    return parts


def _discord_post(token: str, channel: str, content: str) -> None:
    req = urllib.request.Request(
        f"{DISCORD_API}/channels/{channel}/messages",
        data=json.dumps({"content": content}).encode("utf-8"),
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "hn-brief/1.0 (+hermes-agent)",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30)


def post_discord(token: str, channel: str, text: str) -> int:
    """Post the briefing to the channel, chunked. Returns the number of messages."""
    parts = split_for_discord(text)
    n = len(parts)
    for i, part in enumerate(parts, 1):
        body = part if n == 1 else f"{part}\n({i}/{n})"
        for attempt in range(5):
            try:
                _discord_post(token, channel, body)
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429:  # rate limited — honour retry_after
                    try:
                        wait = float(json.loads(exc.read() or b"{}").get("retry_after", 2))
                    except Exception:  # noqa: BLE001
                        wait = 2.0
                    time.sleep(min(max(wait, 1.0), 10.0))
                    continue
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "ignore")[:200]
                except Exception:  # noqa: BLE001
                    pass
                raise RuntimeError(f"HTTP {exc.code} from Discord: {detail}") from exc
        if n > 1:
            time.sleep(1.0)  # stay under the per-channel bucket (~5 req / 5 s)
    return n


# ── transport: Signal (the Daily Notices group) ──────────────────────────────

def send_signal(target: str, text: str, limit: int = SIGNAL_SAFE_LIMIT) -> int:
    """Post the briefing to Signal through `hermes send`, chunked for a phone.

    `hermes send` reuses the gateway's own Signal credentials, so no token is
    needed here and nothing is written to disk. Returns the message count.
    """
    parts = split_for_discord(text, limit)
    n = len(parts)
    for i, part in enumerate(parts, 1):
        body = part if n == 1 else f"[{i}/{n}]\n{part}"
        try:
            proc = subprocess.run(["hermes", "send", "-t", target, "-q", "--", body],
                                  capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"hermes send timed out on chunk {i}/{n}") from exc
        if proc.returncode != 0:
            lines = [ln for ln in (proc.stderr or proc.stdout or "").splitlines() if ln.strip()]
            raise RuntimeError(f"hermes send rc={proc.returncode} on chunk {i}/{n}: "
                               f"{lines[-1][:200] if lines else 'no output'}")
        if n > 1:
            time.sleep(1.0)
    return n


# ── state ────────────────────────────────────────────────────────────────────

def _read_state(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("last_sent")
    except (json.JSONDecodeError, OSError):
        return None


def _write_state(path: Path, date: str, dest: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_sent": date, "sent_at": datetime.now(NY).isoformat(timespec="seconds"), "to": dest}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="HN Brief daily delivery — email + the Daily Channel + Signal")
    ap.add_argument("--to", default=os.environ.get("HN_BRIEF_EMAIL_TO", DEFAULT_TO))
    ap.add_argument("--targets", default=os.environ.get("HN_BRIEF_TARGETS", "email,discord,signal"),
                    help="comma list of targets: email, discord, signal")
    ap.add_argument("--channel", default=os.environ.get("HN_BRIEF_DISCORD_CHANNEL", DEFAULT_DISCORD_CHANNEL),
                    help="Discord channel id for the Daily Channel")
    ap.add_argument("--signal-target", default=os.environ.get("HN_BRIEF_SIGNAL_TARGET", DEFAULT_SIGNAL_TARGET),
                    help="Signal target for the briefing (name or group id)")
    ap.add_argument("--summary-chars", type=int,
                    default=int(os.environ.get("HN_BRIEF_SUMMARY_CHARS", DEFAULT_SUMMARY_CHARS)),
                    help="per-story ARTICLE summary clip, email + Discord (0 = omit)")
    ap.add_argument("--discussion-chars", type=int,
                    default=int(os.environ.get("HN_BRIEF_DISCUSSION_CHARS", DEFAULT_DISCUSSION_CHARS)),
                    help="per-story discussion summary clip, email + Discord (0 = omit)")
    ap.add_argument("--comments", type=int, default=int(os.environ.get("HN_BRIEF_COMMENTS", DEFAULT_COMMENTS)),
                    help="verbatim top comments shown per story (0 = none)")
    ap.add_argument("--comment-chars", type=int,
                    default=int(os.environ.get("HN_BRIEF_COMMENT_CHARS", DEFAULT_COMMENT_CHARS)),
                    help="clip per verbatim comment")
    ap.add_argument("--signal-summary-chars", type=int,
                    default=int(os.environ.get("HN_BRIEF_SIGNAL_SUMMARY_CHARS", DEFAULT_SIGNAL_SUMMARY_CHARS)),
                    help="per-story article summary clip for Signal")
    ap.add_argument("--signal-discussion-chars", type=int,
                    default=int(os.environ.get("HN_BRIEF_SIGNAL_DISCUSSION_CHARS", DEFAULT_SIGNAL_DISCUSSION_CHARS)),
                    help="per-story discussion clip for Signal")
    ap.add_argument("--signal-comments", type=int,
                    default=int(os.environ.get("HN_BRIEF_SIGNAL_COMMENTS", DEFAULT_SIGNAL_COMMENTS)),
                    help="verbatim top comments per story on Signal (0 = none)")
    ap.add_argument("--signal-comment-chars", type=int,
                    default=int(os.environ.get("HN_BRIEF_SIGNAL_COMMENT_CHARS", DEFAULT_SIGNAL_COMMENT_CHARS)),
                    help="clip per verbatim comment on Signal")
    ap.add_argument("--signal-digest-chars", type=int,
                    default=int(os.environ.get("HN_BRIEF_SIGNAL_DIGEST_CHARS", DEFAULT_SIGNAL_DIGEST_CHARS)),
                    help="digest head sent to Signal (0 = the whole essay)")
    ap.add_argument("--dry-run", action="store_true", help="render only, never send")
    ap.add_argument("--force", action="store_true", help="send even if already sent today")
    ap.add_argument("--allow-stale", action="store_true",
                    help="send even when the briefing date is not today (manual re-post or transport test)")
    args = ap.parse_args()
    targets = {t.strip().lower() for t in args.targets.split(",") if t.strip()}

    if not DATA_ROOT.exists():
        log(f"dataset root {DATA_ROOT} not mounted")
        return 2
    meta = json.loads((DATA_ROOT / "latest.json").read_text(encoding="utf-8"))
    day = json.loads((DATA_ROOT / meta["path"]).read_text(encoding="utf-8"))
    date = day["date"]
    today = datetime.now(NY).strftime("%Y-%m-%d")
    subject = f"HN Brief — {date}"

    if date != today:
        if not args.allow_stale:
            log(f"skip: briefing date {date} != today {today} in America/New_York (retry window covers 08:15/09:15)")
            return 0
        log(f"WARNING: --allow-stale — sending the {date} briefing even though today is {today}")
    if not (day.get("quality") or {}).get("digestValid", False):
        log(f"skip: digestValid=false for {date}")
        return 0

    plain = build_plain(day, summary_chars=args.summary_chars,
                        discussion_chars=args.discussion_chars, comments=args.comments,
                        comment_chars=args.comment_chars)
    signal_text = build_plain(
        day,
        summary_chars=args.signal_summary_chars,
        discussion_chars=args.signal_discussion_chars,
        comments=args.signal_comments,
        comment_chars=args.signal_comment_chars,
        digest_chars=args.signal_digest_chars,
        digest_note=("\n\n(full digest in the HN Brief email and the Discord "
                     "#hacker-news channel)"),
    )
    html_body = build_html(day, summary_chars=args.summary_chars,
                           discussion_chars=args.discussion_chars,
                           comments=args.comments, comment_chars=args.comment_chars)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{date}.txt").write_text(f"To: {args.to}\nSubject: {subject}\n\n{plain}", encoding="utf-8")
    (CACHE_DIR / f"{date}.html").write_text(html_body, encoding="utf-8")
    (CACHE_DIR / f"{date}.signal.txt").write_text(signal_text, encoding="utf-8")

    if args.dry_run:
        print(f"rendered {CACHE_DIR / (date + '.txt')} "
              f"({len(plain)} chars plain, {len(signal_text)} chars signal, "
              f"{len(html_body)} chars html; "
              f"{len(split_for_discord(plain))} Discord chunk(s), "
              f"{len(split_for_discord(signal_text, SIGNAL_SAFE_LIMIT))} Signal chunk(s)) "
              f"targets={sorted(targets)}")
        return 0

    failures: list[str] = []
    done: list[str] = []

    if "email" in targets:
        if _read_state(STATE) == date and not args.force:
            log(f"skip email: {date} already sent")
        else:
            cfg = smtp_config()
            missing = [k for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD") if not cfg.get(k)]
            if missing:
                log(f"NOT SENT {date}: SMTP not configured (missing {', '.join(missing)}); "
                    f"expected SMTP_* (or EMAIL_*) in the process env or one of "
                    f"{', '.join(str(p) for p in CRED_SOURCES)}")
            else:
                try:
                    how = send_smtp(cfg, args.to, subject, plain, html_body)
                except Exception as exc:  # noqa: BLE001 — credentials never appear in these messages
                    log(f"EMAIL SEND FAILED {date} to {args.to}: {type(exc).__name__}: {exc}")
                    failures.append(f"email: {type(exc).__name__}: {exc}")
                    print(f"HN Brief email NOT sent ({date}): {type(exc).__name__}: {exc}")
                else:
                    _write_state(STATE, date, args.to)
                    log(f"email sent {date} to {args.to} via {how} ({len(plain)} chars plain / {len(html_body)} chars html)")
                    done.append(f"email→{args.to}")

    if "discord" in targets:
        if _read_state(DISCORD_STATE) == date and not args.force:
            log(f"skip discord: {date} already posted")
        else:
            token = discord_token()
            if not token:
                log(f"DISCORD POST FAILED {date}: DISCORD_BOT_TOKEN not found in "
                    f"{', '.join(str(p) for p in CRED_SOURCES)} or the process env")
                failures.append("discord: DISCORD_BOT_TOKEN missing")
                print(f"HN Brief channel NOT posted ({date}): DISCORD_BOT_TOKEN missing")
            else:
                try:
                    n = post_discord(token, args.channel, plain)
                except Exception as exc:  # noqa: BLE001
                    log(f"DISCORD POST FAILED {date} to channel {args.channel}: {type(exc).__name__}: {exc}")
                    failures.append(f"discord: {type(exc).__name__}: {exc}")
                    print(f"HN Brief channel NOT posted ({date}): {type(exc).__name__}: {exc}")
                else:
                    _write_state(DISCORD_STATE, date, f"discord:{args.channel}")
                    log(f"discord posted {date} to channel {args.channel} ({n} message(s), {len(plain)} chars)")
                    done.append(f"discord→{args.channel} ({n} msg)")

    if "signal" in targets:
        if _read_state(SIGNAL_STATE) == date and not args.force:
            log(f"skip signal: {date} already posted")
        else:
            try:
                n = send_signal(args.signal_target, signal_text)
            except Exception as exc:  # noqa: BLE001
                log(f"SIGNAL POST FAILED {date} to {args.signal_target}: {type(exc).__name__}: {exc}")
                failures.append(f"signal: {type(exc).__name__}: {exc}")
                print(f"HN Brief Signal NOT posted ({date}): {type(exc).__name__}: {exc}")
            else:
                _write_state(SIGNAL_STATE, date, args.signal_target)
                log(f"signal posted {date} to {args.signal_target} ({n} message(s), {len(signal_text)} chars)")
                done.append(f"signal→{args.signal_target} ({n} msg)")

    if done:
        print(f"HN Brief — {date} delivered: " + ", ".join(done))
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
