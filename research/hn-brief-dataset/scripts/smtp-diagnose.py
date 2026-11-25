#!/usr/bin/env python3
"""SMTP diagnostics for the HN Brief email job — never prints the password.

Shows, in order: which credential sources resolved, the TCP banner, the EHLO
capabilities, the STARTTLS certificate, and the raw AUTH exchange with Gmail's
own response codes. Run this when `hn-brief-email.py` reports a send failure:

    python3 <skill>/scripts/smtp-diagnose.py

Reads credentials from the same places as hn-brief-email.py (process env,
/opt/data/secrets/mail.env, /opt/data/.env, /opt/data/secrets/hermes.env).
"""
from __future__ import annotations

import base64
import importlib.util
import socket
import ssl
import sys
from pathlib import Path

EMAIL_SCRIPT = Path(__file__).with_name("hn-brief-email.py")

def load_email_module():
    spec = importlib.util.spec_from_file_location("hn_brief_email", EMAIL_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    m = load_email_module()
    cfg = m.smtp_config()
    host = cfg.get("SMTP_HOST", "smtp.gmail.com")
    port = int(cfg.get("SMTP_PORT") or 587)
    print("sources checked:", ", ".join(str(p) for p in m.CRED_SOURCES))
    for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_FROM"):
        print(f"  {key} = {cfg.get(key, '<unset>')}")
    print(f"  SMTP_PASSWORD = {'<set, len=%d>' % len(cfg['SMTP_PASSWORD']) if cfg.get('SMTP_PASSWORD') else '<unset>'}")
    if not (cfg.get("SMTP_USER") and cfg.get("SMTP_PASSWORD")):
        print("RESULT: incomplete credentials — nothing to test")
        return 1

    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=25) as sock:
            sock.settimeout(25)
            f = sock.makefile("rwb")
            print("banner:", f.readline().decode(errors="ignore").strip())
            f.write(b"EHLO hn-brief-diagnose\r\n")
            f.flush()
            while True:
                line = f.readline().decode(errors="ignore").strip()
                if not line:
                    break
                print("  ", line)
                if not line.startswith("250-"):
                    break
            f.write(b"STARTTLS\r\n")
            f.flush()
            print("STARTTLS:", f.readline().decode(errors="ignore").strip())
            tls = ctx.wrap_socket(sock, server_hostname=host)
            print("TLS:", tls.version(), tls.cipher()[0])
            cert = tls.getpeercert()
            print("cert issuer:", cert.get("issuer"))
            print("cert subject:", cert.get("subject"))
            f = tls.makefile("rwb")
            f.write(b"EHLO hn-brief-diagnose\r\n")
            f.flush()
            while f.readline().decode(errors="ignore").startswith("250-"):
                pass
            f.write(b"NOOP\r\n")
            f.flush()
            print("NOOP:", f.readline().decode(errors="ignore").strip())
            f.write(b"AUTH LOGIN\r\n")
            f.flush()
            print("AUTH LOGIN:", f.readline().decode(errors="ignore").strip())
            f.write(base64.b64encode(cfg["SMTP_USER"].encode()) + b"\r\n")
            f.flush()
            print("user sent:", f.readline().decode(errors="ignore").strip())
            f.write(base64.b64encode(cfg["SMTP_PASSWORD"].encode()) + b"\r\n")
            f.flush()
            reply = f.readline().decode(errors="ignore").strip()
            print("password sent:", reply)
            if reply.startswith("235"):
                print("RESULT: AUTH OK — credentials are valid")
                return 0
            print("RESULT: AUTH REJECTED — see the response code above")
            print("  535-5.7.8 = wrong/revoked app password, or SMTP_USER is not that account")
            return 1
    except Exception as exc:  # noqa: BLE001
        print("TRANSPORT FAILED:", type(exc).__name__, exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
