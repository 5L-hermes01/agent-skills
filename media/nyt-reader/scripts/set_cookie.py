#!/usr/bin/env python3
"""Update NYT cookie env vars in .env from a pasted browser cookie header.

Usage:
    # Pipe from clipboard:
    pbpaste | python scripts/set_cookie.py

    # Interactive:
    python scripts/set_cookie.py

    # From a file:
    python scripts/set_cookie.py path/to/cookie.txt

Accepts:
    - A raw Cookie header value: `name1=val1; name2=val2; ...`
    - A `Cookie: ...` line copied straight from DevTools.

Extracts the five named cookies (nyt-a, NYT-S, nyt-jkidd, nyt-purr, nyt-b-sid)
and writes them as NYT_A/NYT_S/NYT_JKIDD/NYT_PURR/NYT_B_SID in .env.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Browser cookie name -> .env variable name.
COOKIE_TO_ENV = {
    "nyt-a": "NYT_A",
    "NYT-S": "NYT_S",
    "nyt-jkidd": "NYT_JKIDD",
    "nyt-purr": "NYT_PURR",
    "nyt-b-sid": "NYT_B_SID",
}


def parse(raw: str) -> dict[str, str]:
    raw = raw.strip()
    if not raw:
        return {}
    # Strip a leading "Cookie:" header label if present, per-line and combined.
    lines = [re.sub(r"^\s*(set-)?cookie\s*:\s*", "", line, flags=re.IGNORECASE)
             for line in raw.splitlines()]
    joined = "; ".join(line for line in lines if line.strip())
    joined = re.sub(r"^\s*(set-)?cookie\s*:\s*", "", joined, flags=re.IGNORECASE)

    out: dict[str, str] = {}
    for part in joined.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name, value = name.strip(), value.strip()
        if name.lower() in {"path", "domain", "expires", "max-age", "samesite", "secure", "httponly"}:
            continue
        if name and value:
            out[name] = value
    return out


def update_env(env_path: Path, cookies: dict[str, str], dry_run: bool = False) -> str:
    updates: dict[str, str] = {}
    for browser_name, env_name in COOKIE_TO_ENV.items():
        if browser_name in cookies:
            updates[env_name] = cookies[browser_name]

    existing = env_path.read_text() if env_path.exists() else ""
    out_lines: list[str] = []
    seen: set[str] = set()
    for line in existing.splitlines():
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
            "Paste your NYT Cookie header value below.\n"
            "End with Ctrl-D (Unix) or Ctrl-Z then Enter (Windows).\n",
            file=sys.stderr,
        )
        raw = sys.stdin.read()

    cookies = parse(raw)
    if not cookies:
        print("ERROR: no cookies parsed from input.", file=sys.stderr)
        return 1

    found = [c for c in COOKIE_TO_ENV if c in cookies]
    missing = [c for c in COOKIE_TO_ENV if c not in cookies]
    if missing:
        print(
            f"WARNING: missing expected cookie(s): {', '.join(missing)}. "
            "The skill will report SESSION_EXPIRED until all five are set.",
            file=sys.stderr,
        )

    env_path = Path(__file__).resolve().parent.parent / ".env"
    body = update_env(env_path, cookies, dry_run=dry_run)
    print(f"Found {len(found)}/5 NYT cookies.", file=sys.stderr)
    if dry_run:
        print("(dry-run; not writing)", file=sys.stderr)
        print(body)
    else:
        print(f"Wrote {env_path} (mode 600).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
