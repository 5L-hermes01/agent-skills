#!/usr/bin/env python3
"""Verify an outbound email really landed — read the account's Sent folder.

A 250 from the SMTP server means "accepted", not "delivered". This logs in over
IMAP (read-only), finds the Sent mailbox and looks for a subject substring.

Usage:
    python3 verify-sent.py "Weekly digest" ["another subject"]

imaplib pitfall: `SEARCH ALL` over a large mailbox blows the client's 1 MB
reply-line limit and dies with `got more than 1000000 bytes`. Search a narrow
criterion (SUBJECT, then SINCE) and fetch with BODY.PEEK so verification never
marks a message as read. Passwords are read from the env files and never printed.
"""
from __future__ import annotations

import email
import imaplib
import os
import sys
from email.header import decode_header
from pathlib import Path

HOME = Path(os.environ.get("HERMES_HOME", "/opt/data"))
SOURCES = (
    HOME / "secrets" / "mail.env",
    HOME / ".env",
    HOME / ".hermes" / ".env",
)
USER_KEYS = ("EMAIL_ADDRESS", "SMTP_USER")
PWD_KEYS = ("EMAIL_PASSWORD", "SMTP_PASSWORD")
HOST_KEYS = ("EMAIL_IMAP_HOST", "IMAP_HOST")


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


def resolve() -> dict[str, str]:
    raw: dict[str, str] = {}
    for path in SOURCES:
        for key, val in parse_env_file(path).items():
            if val and key not in raw:
                raw[key] = val
    for key, val in os.environ.items():
        if val and key not in raw:
            raw[key] = val
    return raw


def dec(raw_value) -> str:
    if not raw_value:
        return ""
    return "".join(
        part.decode(enc or "utf-8", "ignore") if isinstance(part, bytes) else part
        for part, enc in decode_header(raw_value)
    )


def first(raw: dict[str, str], keys) -> str:
    for k in keys:
        if raw.get(k):
            return raw[k]
    return ""


def main() -> int:
    needles = sys.argv[1:] or [""]
    raw = resolve()
    user = first(raw, USER_KEYS)
    pwd = first(raw, PWD_KEYS)
    host = first(raw, HOST_KEYS) or ("imap." + user.split("@")[1] if "@" in user else "")
    if not (user and pwd and host):
        print("credentials incomplete: need an address, a password and an IMAP host")
        return 1

    M = imaplib.IMAP4_SSL(host, 993)
    M.login(user, pwd)
    print("IMAP login OK as", user)
    _, boxes = M.list()
    sent_box = None
    for box in boxes:
        line = box.decode(errors="ignore")
        if "\\Sent" in line:
            sent_box = line.split(' "/" ')[-1].strip().strip('"')
    if not sent_box:
        print("no sent mailbox found")
        return 1
    M.select(f'"{sent_box}"', readonly=True)
    print("sent folder:", sent_box)

    found = []
    for needle in needles:
        criteria = f'(SUBJECT "{needle}")' if needle else '(SINCE 1-Jan-2000)'
        _, data = M.search(None, criteria)
        ids = (data[0].split() if data and data[0] else [])[-25:]
        for i in ids:
            _, md = M.fetch(i, "(BODY.PEEK[HEADER.FIELDS (SUBJECT TO DATE)])")
            if not md or not isinstance(md[0], tuple):
                continue
            msg = email.message_from_bytes(md[0][1])
            subject = dec(msg.get("Subject"))
            if needle.lower() in subject.lower():
                found.append((i.decode(), subject, dec(msg.get("To")), msg.get("Date")))
    M.logout()

    print("matches:", len(found))
    for row in found:
        print("  id=%s | subject=%s | to=%s | date=%s" % row)
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
