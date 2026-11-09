#!/usr/bin/env python3
"""Probe local LLM box: latency per explicit model id.

Usage: probe_models.py [host] [model ...]
Model list is loaded from scripts/probe_models.json (edit THAT file, not this
script). CLI args override host/models. Slow/broken aliases (qwen3.8,
qwen3.5-35b-a3b) are intentionally absent from the default list - run e.g.
`probe_models.py 192.168.100.10:11434 qwen3.8` to demonstrate why aliases
must not be trusted.
"""
import json
import os
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "probe_models.json")


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"host": "192.168.100.10:11434", "models": []}


cfg = load_config()
HOST = sys.argv[1] if len(sys.argv) > 1 else cfg.get("host", "192.168.100.10:11434")
models = sys.argv[2:] or cfg.get("models", [])

if not models:
    print(f"no models configured ({CONFIG_PATH}); pass ids on CLI", file=sys.stderr)
    sys.exit(2)

for m in models:
    body = {
        "model": m,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 8,
        "temperature": 0,
    }
    t0 = time.time()
    try:
        r = subprocess.run(
            ["curl", "-s", "-m", "60",
             f"http://{HOST}/v1/chat/completions",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(body)],
            capture_output=True, text=True, timeout=65,
        )
        dt = time.time() - t0
        ok = '"choices"' in r.stdout
        print(f"{m:45s} {dt:5.1f}s {'OK' if ok else 'FAIL'} {r.stdout[:80]}")
    except Exception as e:
        print(f"{m:45s} TIMEOUT/ERR {e}")