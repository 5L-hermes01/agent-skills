#!/usr/bin/env python3
"""Update WSJ_COOKIE in .env from a pasted browser cookie header.

Usage:
    pbpaste | python scripts/set_cookie.py
    python scripts/set_cookie.py path/to/cookie.txt
    python scripts/set_cookie.py            # interactive paste, Ctrl-D to end

Accepts a raw `Cookie:` header value (with or without the leading label).
Writes it verbatim as WSJ_COOKIE into .env (mode 600). WSJ requires the
full cookie jar — we don't try to extract a named subset.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def parse(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    # If we got a Cookie: header line, strip the label. Join multiple lines.
    lines = [re.sub(r"^\s*(set-)?cookie\s*:\s*", "", line, flags=re.IGNORECASE)
             for line in raw.splitlines()]
    return "; ".join(line.strip() for line in lines if line.strip())


def update_env(env_path: Path, cookie_value: str, dry_run: bool = False) -> str:
    existing = env_path.read_text() if env_path.exists() else ""
    out_lines: list[str] = []
    seen = False
    for line in existing.splitlines():
        m = re.match(r"\s*WSJ_COOKIE\s*=", line)
        if m:
            out_lines.append(f"WSJ_COOKIE={cookie_value}")
            seen = True
        else:
            out_lines.append(line)
    if not seen:
        out_lines.append(f"WSJ_COOKIE={cookie_value}")
    body = "\n".join(out_lines).rstrip() + "\n"

    if dry_run:
        return body

    env_path.write_text(body)
    os.chmod(env_path, 0o600)
    return body


def main() -> int:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    if args:
        raw = Path(args[0]).read_text()
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        print(
            "Paste your WSJ Cookie header value below.\n"
            "End with Ctrl-D (Unix) or Ctrl-Z then Enter (Windows).\n",
            file=sys.stderr,
        )
        raw = sys.stdin.read()

    cookie = parse(raw)
    if not cookie or len(cookie) < 50:
        print(
            f"ERROR: cookie too short ({len(cookie)} chars). WSJ usually needs 3000+ characters.",
            file=sys.stderr,
        )
        return 1

    env_path = Path(__file__).resolve().parent.parent / ".env"
    body = update_env(env_path, cookie, dry_run=dry_run)
    print(f"Parsed WSJ cookie ({len(cookie)} chars).", file=sys.stderr)
    if dry_run:
        print("(dry-run; not writing)", file=sys.stderr)
        print(body)
    else:
        print(f"Wrote {env_path} (mode 600).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
