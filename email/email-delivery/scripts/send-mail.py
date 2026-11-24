#!/usr/bin/env python3
"""send-mail.py — one-shot outbound mail from the shell. Send-only transport.

Use this instead of `hermes send -t email:<addr>`: that target is gated on
`platforms.email.enabled`, and this host deliberately runs the email platform
disabled (enabled=true would also switch on IMAP polling of a shared inbox).

    python3 send-mail.py --to nick@example.com --subject "Deploy done" \
        --body "The 03:00 build passed." [--attach /path/report.pdf] [--html body.html]
    python3 send-mail.py --to a@b --subject s --body-file /tmp/body.txt --dry-run

Credentials: same sources and precedence as the briefing script —
/opt/data/secrets/mail.env, /opt/data/.env, /opt/data/secrets/hermes.env, then
the process environment. Accepts SMTP_* and EMAIL_* namings. The password is only
ever handed to smtplib.login(); it is never printed, logged or cached.
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

CRED_SOURCES = (
    Path("/opt/data/secrets/mail.env"),
    Path("/opt/data/.env"),
    Path("/opt/data/secrets/hermes.env"),
)
KEY_ALIASES = {
    "SMTP_HOST": ("SMTP_HOST", "EMAIL_SMTP_HOST"),
    "SMTP_PORT": ("SMTP_PORT", "EMAIL_SMTP_PORT"),
    "SMTP_USER": ("SMTP_USER", "EMAIL_ADDRESS", "EMAIL_USER"),
    "SMTP_PASSWORD": ("SMTP_PASSWORD", "EMAIL_PASSWORD"),
    "SMTP_FROM": ("SMTP_FROM", "EMAIL_FROM", "EMAIL_ADDRESS", "EMAIL_HOME_ADDRESS"),
}


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


def smtp_config() -> tuple[dict[str, str], dict[str, str]]:
    raw: dict[str, str] = {}
    source: dict[str, str] = {}
    for path in CRED_SOURCES:  # files win — the process env is a boot snapshot
        for key, val in parse_env_file(path).items():
            if val and key not in raw:
                raw[key] = val
                source[key] = str(path)
    for key, val in os.environ.items():
        if val and key not in raw:
            raw[key] = val
            source[key] = "process env"
    cfg: dict[str, str] = {}
    for canon, names in KEY_ALIASES.items():
        for name in names:
            if raw.get(name):
                cfg[canon] = raw[name]
                source[canon] = source.get(name, "?")
                break
    return cfg, source


def main() -> int:
    ap = argparse.ArgumentParser(description="Send one email via SMTP")
    ap.add_argument("--to", required=True, action="append", help="recipient (repeatable)")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", help="plain-text body")
    ap.add_argument("--body-file", help="read the plain-text body from this file")
    ap.add_argument("--html", help="optional HTML body (raw HTML)")
    ap.add_argument("--attach", action="append", default=[], help="file to attach (repeatable)")
    ap.add_argument("--from", dest="sender", help="override the From address")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    elif args.body:
        body = args.body
    else:
        body = sys.stdin.read()
    if not body.strip():
        print("refusing to send an empty message", file=sys.stderr)
        return 2

    cfg, source = smtp_config()
    missing = [k for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD") if not cfg.get(k)]
    if missing:
        print(f"SMTP not configured (missing {', '.join(missing)}); sources checked: "
              f"{', '.join(str(p) for p in CRED_SOURCES)} + process env", file=sys.stderr)
        return 2

    sender = args.sender or cfg.get("SMTP_FROM") or cfg["SMTP_USER"]
    msg = EmailMessage()
    msg["From"] = formataddr(("Hermes", sender))
    msg["To"] = ", ".join(args.to)
    msg["Subject"] = args.subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(body)
    if args.html:
        msg.add_alternative(args.html, subtype="html")
    for path in args.attach:
        p = Path(path)
        ctype, _ = mimetypes.guess_type(p.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)

    if args.dry_run:
        print(f"dry-run: to={msg['To']} subject={msg['Subject']!r} sender={sender} "
              f"attachments={len(args.attach)} body_chars={len(body)} "
              f"creds_from={ {k: v for k, v in source.items() if k in ('SMTP_HOST','SMTP_USER','SMTP_PASSWORD')} }")
        return 0

    host = cfg["SMTP_HOST"]
    port = int(cfg.get("SMTP_PORT") or 587)
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=60, context=ssl.create_default_context()) as s:
                s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=60) as s:
                s.ehlo()
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
                s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        print(f"login rejected by {host}: {exc.smtp_code} (check the app password)", file=sys.stderr)
        return 2
    except smtplib.SMTPServerDisconnected:
        print(f"connection closed during AUTH on {host}:{port} — usually a rejected login "
              f"(bad/revoked app password); run smtp-probe.py for the server's response code", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"send failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"sent to {msg['To']} via {host}:{port} as {sender}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
