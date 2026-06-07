#!/usr/bin/env python3
"""Update FT_COOKIE in .env from a pasted browser cookie header.

Usage:
    # Interactive: paste the Cookie header value, Ctrl-D when done.
    python scripts/set_cookie.py

    # Pipe from clipboard (macOS):
    pbpaste | python scripts/set_cookie.py

    # From a file:
    python scripts/set_cookie.py path/to/cookie.txt

Accepts:
    - A raw Cookie header value: `name1=val1; name2=val2; ...`
    - A `Cookie: ...` line copied straight from DevTools.
    - Multi-line `Set-Cookie:` style headers (one cookie per line).
    - A simple JSON object: {"FTSession_s": "...", ...}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REQUIRED_NAMED = {
    "FTSession_s": "FT_SESSION_S",
    "FTClientSessionId": "FT_CLIENT_SESSION_ID",
    "AppUser": "FT_APP_USER",
    "_csrf": "FT_CSRF",
}


def parse(raw: str) -> dict[str, str]:
    raw = raw.strip()
    if not raw:
        return {}

    # JSON object?
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
            return {str(k): str(v) for k, v in obj.items()}
        except json.JSONDecodeError:
            pass

    cookies: dict[str, str] = {}

    # Strip a leading "Cookie:" header label if present, anywhere on each line.
    lines = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*(set-)?cookie\s*:\s*", "", line, flags=re.IGNORECASE)
        if line.strip():
            lines.append(line)

    joined = "; ".join(lines) if len(lines) > 1 else raw
    # Strip a leading label on the joined form too.
    joined = re.sub(r"^\s*(set-)?cookie\s*:\s*", "", joined, flags=re.IGNORECASE)

    for part in joined.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name, value = name.strip(), value.strip()
        # Drop Set-Cookie attribute words.
        if name.lower() in {"path", "domain", "expires", "max-age", "samesite", "secure", "httponly"}:
            continue
        if name and value:
            cookies[name] = value
    return cookies


def update_env(env_path: Path, cookies: dict[str, str], dry_run: bool = False) -> str:
    """Set FT_COOKIE and the four named legacy vars. Preserve other lines."""
    blob = "; ".join(f"{k}={v}" for k, v in cookies.items())
    updates = {"FT_COOKIE": blob}
    for browser_name, env_name in REQUIRED_NAMED.items():
        if browser_name in cookies:
            updates[env_name] = cookies[browser_name]

    existing = env_path.read_text() if env_path.exists() else ""
    lines = existing.splitlines() if existing else []
    seen: set[str] = set()
    out_lines: list[str] = []
    for line in lines:
        m = re.match(r"\s*([A-Z_][A-Z0-9_]*)\s*=", line)
        if m and m.group(1) in updates:
            key = m.group(1)
            out_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out_lines.append(line)
    for key, val in updates.items():
        if key not in seen:
            out_lines.append(f"{key}={val}")
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
            "Paste your FT Cookie header value below.\n"
            "End with Ctrl-D (Unix) or Ctrl-Z then Enter (Windows).\n",
            file=sys.stderr,
        )
        raw = sys.stdin.read()

    cookies = parse(raw)
    if not cookies:
        print("ERROR: no cookies parsed from input.", file=sys.stderr)
        return 1

    missing = [n for n in REQUIRED_NAMED if n not in cookies]
    if missing:
        print(
            f"WARNING: missing expected cookie(s): {', '.join(missing)}. "
            "FT_COOKIE will still be set; legacy named vars will be partial.",
            file=sys.stderr,
        )

    env_path = Path(__file__).resolve().parent.parent / ".env"
    body = update_env(env_path, cookies, dry_run=dry_run)

    print(f"Parsed {len(cookies)} cookies.", file=sys.stderr)
    if dry_run:
        print("(dry-run; not writing)", file=sys.stderr)
        print(body)
    else:
        print(f"Wrote {env_path} (mode 600).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
