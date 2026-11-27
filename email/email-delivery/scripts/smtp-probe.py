#!/usr/bin/env python3
"""SMTP transport probe — find WHERE a send dies, without printing the password.

Prints, in order: which source each credential came from, the TCP banner, the
EHLO capabilities, the STARTTLS certificate (a self-signed or unexpected issuer
means TLS interception), a NOOP, then a raw AUTH LOGIN exchange with the
server's own response codes.

Why this exists: Gmail closes the socket immediately after a 535, so
`smtplib.login()` raises SMTPServerDisconnected instead of SMTPAuthenticationError
and a credential problem reads as a network problem. This shows the real code
(535 = rejected login).

Usage:
    python3 smtp-probe.py              # host/port from the env files
    python3 smtp-probe.py host 587

Credential lookup (files win over the process environment, which is a snapshot
from when the gateway started): $HERMES_HOME/secrets/mail.env, /opt/data/.env,
$HERMES_HOME/.env, then the process env. Both namings are accepted:
SMTP_HOST/PORT/USER/PASSWORD and EMAIL_SMTP_HOST/EMAIL_SMTP_PORT/EMAIL_ADDRESS/
EMAIL_PASSWORD.
"""
from __future__ import annotations

import base64
import os
import socket
import ssl
import sys
from pathlib import Path

HOME = Path(os.environ.get("HERMES_HOME", "/opt/data"))
SOURCES = (
    HOME / "secrets" / "mail.env",
    HOME / ".env",
    HOME / ".hermes" / ".env",
)
ALIASES = {
    "host": ("SMTP_HOST", "EMAIL_SMTP_HOST"),
    "port": ("SMTP_PORT", "EMAIL_SMTP_PORT"),
    "user": ("SMTP_USER", "EMAIL_ADDRESS", "EMAIL_USER"),
    "password": ("SMTP_PASSWORD", "EMAIL_PASSWORD"),
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


def resolve() -> tuple[dict[str, str], dict[str, str]]:
    raw: dict[str, str] = {}
    src: dict[str, str] = {}
    for path in SOURCES:
        for key, val in parse_env_file(path).items():
            if val and key not in raw:
                raw[key] = val
                src[key] = str(path)
    for key, val in os.environ.items():
        if val and key not in raw:
            raw[key] = val
            src[key] = "process env"
    cfg: dict[str, str] = {}
    for canon, names in ALIASES.items():
        for name in names:
            if raw.get(name):
                cfg[canon] = raw[name]
                cfg[f"{canon}_from"] = src.get(name, "?")
                break
    return cfg, src


def main() -> int:
    cfg, _ = resolve()
    if len(sys.argv) > 2:
        cfg["host"], cfg["port"] = sys.argv[1], sys.argv[2]
    host = cfg.get("host", "smtp.gmail.com")
    port = int(cfg.get("port") or 587)
    user = cfg.get("user", "")
    pwd = cfg.get("password", "")

    print("credential sources:")
    for canon in ("host", "port", "user", "password"):
        shown = f"<set, len={len(pwd)}>" if canon == "password" and pwd else cfg.get(canon, "<unset>")
        print(f"  {canon:9s} = {shown} (from {cfg.get(canon + '_from', 'default')})")
    if not (user and pwd):
        print("RESULT: credentials incomplete — nothing to test")
        return 1

    try:
        with socket.create_connection((host, port), timeout=25) as sock:
            sock.settimeout(25)
            f = sock.makefile("rwb")
            print("banner:", f.readline().decode(errors="ignore").strip())
            f.write(b"EHLO email-delivery-probe\r\n")
            f.flush()
            while True:
                line = f.readline().decode(errors="ignore").strip()
                if not line:
                    break
                print("   ", line)
                if not line.startswith("250-"):
                    break
            if port == 465:
                print("implicit TLS port — skipping STARTTLS")
                tls = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            else:
                f.write(b"STARTTLS\r\n")
                f.flush()
                print("STARTTLS:", f.readline().decode(errors="ignore").strip())
                tls = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            print("TLS:", tls.version(), tls.cipher()[0])
            cert = tls.getpeercert()
            print("cert issuer:", cert.get("issuer"))
            print("cert subject:", cert.get("subject"))

            f = tls.makefile("rwb")
            f.write(b"EHLO email-delivery-probe\r\n")
            f.flush()
            while f.readline().decode(errors="ignore").startswith("250-"):
                pass
            f.write(b"NOOP\r\n")
            f.flush()
            print("NOOP:", f.readline().decode(errors="ignore").strip())

            f.write(b"AUTH LOGIN\r\n")
            f.flush()
            print("AUTH LOGIN:", f.readline().decode(errors="ignore").strip())
            f.write(base64.b64encode(user.encode()) + b"\r\n")
            f.flush()
            print("user sent:", f.readline().decode(errors="ignore").strip())
            f.write(base64.b64encode(pwd.encode()) + b"\r\n")
            f.flush()
            reply = f.readline().decode(errors="ignore").strip()
            print("password sent:", reply)
    except Exception as exc:  # noqa: BLE001
        print("TRANSPORT FAILED:", type(exc).__name__, exc)
        return 2

    if reply.startswith("235"):
        print("RESULT: AUTH OK — credentials are valid")
        return 0
    print("RESULT: AUTH REJECTED — see the code above")
    print("  535-5.7.8 = wrong/revoked app password, or the user is not that account")
    return 1


if __name__ == "__main__":
    sys.exit(main())
