#!/usr/bin/env python3
"""Deterministic orchestrator for the WaytoAGI digest pipelines.

Runs the full data-prep chain (fetch -> translate titles/summaries -> fetch full
article content -> translate bodies) and writes the enriched JSON to disk for a
downstream cron LLM to format/deliver.

Usage:
    waytoagi_pipeline.py daily   # -> /tmp/wt_daily_full.json
    waytoagi_pipeline.py weekly  # -> /tmp/wt_week_full.json

Both write /tmp/wt_<scope>_full.json. The cron LLM reads that file and formats
the digest — it never runs the heavy chain itself, so it stays under the
foreground timeout and never needs to background/self-approve.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from waytoagi_translate import _needs_translation

WTR = str(Path(__file__).resolve().parents[1])
# Sibling helper scripts (translate/content) live in the SAME directory as this
# pipeline — in the consumption skill dir (/opt/data/skills/.../scripts/), NOT
# under the repo's scripts/ dir. Resolve them relative to this file so the
# prep works regardless of which copy is invoked.
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
# The waytoagi_reader package lives at <waytoagi-reader dir>/src. The cron venv
# (/opt/hermes/.venv) does NOT have it installed (only the system python does),
# so we must put the reader src on PYTHONPATH for whichever interpreter runs us.
# The reader dir is the parent of scripts/; its src/ sits beside scripts/.
READER_SRC = os.path.join(os.path.dirname(SCRIPTS), "src")
PY = sys.executable  # inherit the interpreter that launched us (cron venv, etc.)
# Merge env so subprocesses can import waytoagi_reader from the consumption copy.
SUBENV = dict(os.environ)
SUBENV["PYTHONPATH"] = READER_SRC + (os.pathsep + SUBENV["PYTHONPATH"]
                                     if SUBENV.get("PYTHONPATH") else "")
HOST = os.environ.get("WAYTOAGI_TRANSLATE_HOST", "http://192.168.100.10:11434")
MODEL = os.environ.get("WAYTOAGI_TRANSLATE_MODEL", "qwen3.8")
OUT = {  # scope -> (output_path, translate args)
    "daily": ("/tmp/wt_daily_full.json", ["--latest-day"]),
    "weekly": ("/tmp/wt_week_full.json", []),
}

# Per-scope subprocess timeouts (seconds). Weekly is far heavier (all items
# vs. one day) and cold-cache runs must not be killed by a daily-sized budget.
TIMEOUTS = {
    "fetch":    {"daily": 130, "weekly": 130},
    "translate": {"daily": 200, "weekly": 900},
    "content":  {"daily": 1100, "weekly": 2400},
}


def run(cmd, **kw):
    kw.setdefault("env", SUBENV)
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] not in OUT:
        print("usage: waytoagi_pipeline.py <daily|weekly>", file=sys.stderr)
        return 2
    scope = args[0]
    out_path, trans_extra = OUT[scope]
    t0 = time.time()

    # 1. fetch flat
    r = run([PY, "-m", "waytoagi_reader.cli", "update-log", "--flatten", "--no-cache"],
            cwd=WTR, timeout=TIMEOUTS["fetch"][scope])
    if r.returncode != 0 or not r.stdout.strip():
        print(f"[err] fetch failed: {r.stderr[-300:]}", file=sys.stderr)
        return 1
    flat = r.stdout

    # 2. translate titles/summaries
    tr = run([PY, f"{SCRIPTS}/waytoagi_translate.py",
              "--host", HOST, "--model", MODEL] + trans_extra,
             input=flat, timeout=TIMEOUTS["translate"][scope])
    if tr.returncode != 0:
        print(f"[err] translate failed: {tr.stderr[-300:]}", file=sys.stderr)
        return 1
    try:
        translated = json.loads(tr.stdout)
        for item in translated["items"]:
            for field in ("title", "summary"):
                if _needs_translation(item.get(field) or ""):
                    if not isinstance(item.get(field + "_en"), str) or not item[field + "_en"].strip():
                        raise ValueError(f"Missing {field}_en")
    except (ValueError, KeyError, TypeError) as e:
        print(f"[err] incomplete title/summary output: {e}", file=sys.stderr)
        return 1
    print(f"[info] {scope}: titles/summaries translated in {time.time()-t0:.0f}s", file=sys.stderr)

    # 3. full article content + translate (the heavy part; this script IS the long runner)
    fc = run([PY, f"{SCRIPTS}/waytoagi_content.py",
              "--host", HOST, "--model", MODEL],
             input=tr.stdout, timeout=TIMEOUTS["content"][scope])
    if fc.returncode != 0:
        print(f"[err] content failed: {fc.stderr[-300:]}", file=sys.stderr)
        return 1
    try:
        enriched = json.loads(fc.stdout)
        if len(enriched["items"]) != len(translated["items"]):
            raise ValueError("Content stage changed item count")
        for source, item in zip(translated["items"], enriched["items"]):
            if any(item.get(key) != value for key, value in source.items() if key not in ("content_zh", "content_en")):
                raise ValueError("Content stage changed source item")
            if source.get("url"):
                for field in ("content_zh", "content_en"):
                    if not isinstance(item.get(field), str) or not item[field].strip():
                        raise ValueError(f"Missing {field}")
    except (ValueError, KeyError, TypeError) as e:
        print(f"[err] incomplete article output: {e}", file=sys.stderr)
        return 1
    print(f"[info] {scope}: content translated in {time.time()-t0:.0f}s", file=sys.stderr)

    output = Path(out_path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=output.name + ".", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write(fc.stdout)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"[info] wrote {out_path} ({time.time()-t0:.0f}s total)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
