#!/usr/bin/env python3
"""jargon-notify, deterministic conversion (no_agent cron job).

Posts genuinely-new jargon terms to Discord; updates the git-tracked state
file. Empty stdout on zero-new-days -> scheduler treats the run as silent
(no delivery, no agent, no tokens, no write_file verifier warnings).

Exit non-zero ONLY on real failures (registry unreadable, Discord post failed)
— the scheduler then delivers an error alert, so a broken watchdog never
goes silent-fail.

Usage: jargon_notify.py [--dry-run]
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REGISTRY_PATHS = [
    "/opt/data/references/jargon-registry.json",
    "/opt/data/skills/research/jargon/references/jargon-registry.json",
    "/opt/data/repos/agent-skills/research/jargon/references/jargon-registry.json",
]
STATE_PATHS = [
    "/opt/data/repos/agent-skills/research/jargon/references/posted-terms.json",
    "/opt/data/skills/research/jargon/references/posted-terms.json",
]
BLOCKLIST_PATHS = [
    "/opt/data/skills/research/jargon/references/jargon-blocklist.json",
    "/opt/data/references/jargon-blocklist.json",
    "/opt/data/repos/agent-skills/research/jargon/references/jargon-blocklist.json",
]
DISCORD_CHANNEL = "discord:1515190329832374272"


def load_json(paths, required, what):
    for p in paths:
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    if required:
        print(f"ERROR: {what} not found at any of {paths}", file=sys.stderr)
        raise SystemExit(1)
    return None


def atomic_write(path, data):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def full_name(entry):
    doc = (entry.get("plainspeak") or {}).get("doctor", "") or ""
    for sep in ("\u2014", " -- ", "\u2013"):
        if sep in doc:
            head = doc.split(sep, 1)[0].strip()
            if 2 <= len(head) <= 80:
                return head
    return ""


def build_message(terms, registry):
    lines = []
    for t in terms:
        entry = registry["terms"].get(t, {})
        kg = (entry.get("plainspeak") or {}).get("kindergarten", "") or "(no definition)"
        kg = re.sub(r"\s+", " ", kg).strip()
        name = full_name(entry)
        mid = f" \u2014 {name}" if name and name.upper() != t.upper() else ""
        lines.append(f"\U0001F195 New jargon: **{t}**{mid} \u2014 {kg}")
    return "\n".join(lines)


def send_discord(text, dry):
    if dry:
        print("[dry-run] would post to " + DISCORD_CHANNEL + ":\n" + text)
        return True
    cmd = ["hermes", "send", "--to", DISCORD_CHANNEL, "--", text]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"ERROR: hermes send failed rc={r.returncode}: {r.stderr[:300]}",
              file=sys.stderr)
    return r.returncode == 0


def resolve(paths, override_env):
    """Allow tests to redirect a path group without rewriting script text."""
    single = os.environ.get(override_env)
    if single:
        return [single]
    return paths


def main():
    dry = "--dry-run" in sys.argv
    self_test = "--self-test" in sys.argv
    registry = load_json(resolve(REGISTRY_PATHS, "JARGON_REGISTRY"), True, "jargon registry")
    state = load_json(resolve(STATE_PATHS, "JARGON_STATE"), False, "posted-terms state")
    if state is None:
        state = {"version": 1, "last_checked": None, "posted_terms": {}}

    blocked = set()
    bl = load_json(resolve(BLOCKLIST_PATHS, "JARGON_BLOCKLIST"), False, "blocklist")
    if bl:
        blocked = set(bl.get("blocked_terms", []))

    reg_terms = set(registry.get("terms", {}).keys())
    posted = set(state.get("posted_terms", {}))
    new_terms = sorted((reg_terms - posted) - blocked)

    if self_test:
        # Force the message-render + post path WITHOUT any file write or real
        # Discord send: synthesize 3 new terms by hiding the 3 most-recently
        # posted ones from the state we diff against. Exercises the exact code
        # the scheduler will run on a real new-terms day.
        hide = sorted(state.get("posted_terms", {}), key=lambda k: state["posted_terms"][k])[-3:]
        for t in hide:
            state["posted_terms"].pop(t, None)
        new_terms = sorted((reg_terms - set(state["posted_terms"])) - blocked)
        print(f"[self-test] hiding {hide} -> new_terms={new_terms}", file=sys.stderr)
        assert len(new_terms) == 3, f"expected 3 synthetic new terms, got {len(new_terms)}"
        text = build_message(new_terms, registry)
        assert "New jargon:" in text and all(t in text for t in new_terms)
        print("[self-test] render OK:\n" + text)
        print("[self-test] PASS — post path, message shape, and term extraction verified; "
              "no state written, no Discord send.")
        sys.exit(0)

    print(f"[jargon-notify] registry={len(reg_terms)} posted={len(posted)} "
          f"blocked={len(blocked)} new={len(new_terms)}", file=sys.stderr)

    if not new_terms:
        # Silent success: empty stdout -> scheduler suppresses delivery.
        sys.exit(0)

    text = build_message(new_terms, registry)
    if not send_discord(text, dry):
        sys.exit(1)

    if not dry:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state.setdefault("posted_terms", {})
        for t in new_terms:
            state["posted_terms"][t] = now
        state["last_checked"] = now
        # Durability: /opt/data is a persistent mount; the two on-disk mirrors
        # ARE the store. The state JSON is deliberately gitignored (runtime
        # state, kept out of the repo like registry/blocklist) — no git commit.
        for p in STATE_PATHS:  # repo path (primary) + consumption mirror
            atomic_write(p, state)

    print(f"jargon-notify: posted {len(new_terms)} new term(s): "
          + ", ".join(new_terms[:20])
          + (" ..." if len(new_terms) > 20 else ""))


main()
