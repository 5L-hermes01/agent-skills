#!/usr/bin/env python3
"""Batch-translate WaytoAGI flat JSON to English via an OpenAI-compatible endpoint.

Reads `waytoagi update-log --flatten` JSON on stdin, batch-translates every Chinese
`title` and `summary` through a local OpenAI-compatible server (default qwen3.8),
and writes the same document to stdout with `title_en` / `summary_en` siblings.

Batching (chunks of 10) makes this ~10x faster than per-string calls. Fully
deterministic with a filesystem translation cache, so re-runs over stable input
are near-instant and cheap.

Usage:
    waytoagi update-log --flatten | waytoagi-translate > out_en.json

Env:
    WAYTOAGI_TRANSLATE_HOST  default http://192.168.100.10:11434
    WAYTOAGI_TRANSLATE_MODEL default qwen3.8
    WAYTOAGI_TRANSLATE_CACHE default $XDG_CACHE_HOME/waytoagi-translate (disable: --no-cache)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_SYSTEM_PROMPT = (
    "You are a precise Chinese-to-English translator. For each numbered item [n] "
    "return exactly one line '[n] <translation>'. Preserve proper nouns, product "
    "names, URLs, and numbers exactly. Return only the numbered translations, no "
    "commentary, no quoting."
)

_ZH_RE = re.compile(r"[\u4e00-\u9fff]")
_FIELDS = ("title", "summary")


def _cache_dir() -> Path:
    base = os.environ.get("WAYTOAGI_TRANSLATE_CACHE")
    if base:
        return Path(base)
    xdg = os.environ.get("XDG_CACHE_HOME")
    root = Path(xdg) if xdg else Path.home() / ".cache"
    return root / "waytoagi-translate"


def _cache_key(text: str, host: str, model: str) -> str:
    h = hashlib.sha256()
    for part in (text, host, model, _SYSTEM_PROMPT):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _cache_get(cache: Path, text: str, host: str, model: str):
    p = cache / "v1" / f"{_cache_key(text, host, model)}.json"
    try:
        return json.loads(p.read_text())["en"]
    except Exception:
        return None


def _cache_put(cache: Path, text: str, host: str, model: str, en: str) -> None:
    p = cache / "v1" / f"{_cache_key(text, host, model)}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"zh": text, "en": en}, ensure_ascii=False))
    tmp.replace(p)


def _needs_translation(s: str) -> bool:
    return bool(s) and len(s) >= 2 and bool(_ZH_RE.search(s))


def _post(host: str, model: str, lines: list[str], timeout: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "Translate to English:\n\n" + "\n".join(lines)},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{host.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read())
    return (body.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()


def _translate_batch(host: str, model: str, texts: list[tuple[int, str]], use_cache: bool) -> dict[int, str]:
    """Return {index: translation} for the (index, zh) pairs needing translation."""
    cache = _cache_dir()
    out: dict[int, str] = {}
    todo = [(i, t) for i, t in texts if _needs_translation(t)]
    if not todo:
        return out

    for i, t in todo:
        if use_cache:
            hit = _cache_get(cache, t, host, model)
            if hit is not None:
                out[i] = hit

    remaining = [(i, t) for i, t in todo if i not in out]
    chunk_size = 10
    for start in range(0, len(remaining), chunk_size):
        chunk = remaining[start:start + chunk_size]
        lines = [f"[{i}] {t}" for i, t in chunk]
        ok = False
        for attempt in range(3):
            try:
                raw = _post(host, model, lines, timeout=120)
                parsed = {int(m.group(1)): m.group(2).strip()
                          for m in re.finditer(r"^\[(\d+)\]\s*(.+)$", raw, re.MULTILINE)}
                for i, _t in chunk:
                    if i in parsed and parsed[i]:
                        out[i] = parsed[i]
                        if use_cache:
                            _cache_put(cache, _t, host, model, parsed[i])
                ok = True
                break
            except Exception as e:
                print(f"[warn] batch {start//chunk_size} attempt {attempt+1} failed: {e}", file=sys.stderr)
                time.sleep(1.0 * (attempt + 1))
        if not ok:
            print(f"[warn] batch {start//chunk_size} failed after retries; falling back per-item", file=sys.stderr)
            for i, t in chunk:
                try:
                    en = _post(host, model, [f"[0] {t}"], timeout=60)
                    m = re.search(r"^\[0\]\s*(.+)$", en, re.MULTILINE)
                    if m:
                        out[i] = m.group(1).strip()
                        if use_cache:
                            _cache_put(cache, t, host, model, out[i])
                except Exception as e2:
                    print(f"[warn] per-item {i} failed: {e2}", file=sys.stderr)
    return out


def translate_doc(doc: dict, host: str, model: str, use_cache: bool, latest_day_only: bool = False) -> dict:
    items = doc.get("items", [])
    if latest_day_only:
        days = sorted({i.get("day") for i in items if i.get("day")}, reverse=True)
        if days:
            latest = days[0]
            items = [i for i in items if i.get("day") == latest]
    # Collect all (zh, field, item_index) triples that need translation.
    # The index passed to the batch translator is the position in the flat list.
    pairs: list[tuple[int, str]] = []          # (flat_idx, zh)
    targets: list[tuple[int, int, str]] = []   # (flat_idx, item_idx, field)
    for item_idx, item in enumerate(items):
        for f in _FIELDS:
            v = item.get(f)
            if isinstance(v, str) and v:
                flat = len(pairs)
                pairs.append((flat, v))
                targets.append((flat, item_idx, f))

    trans = _translate_batch(host, model, pairs, use_cache)
    for flat, item_idx, f in targets:
        if flat in trans:
            items[item_idx][f"{f}_en"] = trans[flat]
    doc["items"] = items
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=os.environ.get("WAYTOAGI_TRANSLATE_HOST", "http://192.168.100.10:11434"))
    ap.add_argument("--model", default=os.environ.get("WAYTOAGI_TRANSLATE_MODEL", "qwen3.8"))
    ap.add_argument("--no-cache", action="store_true", help="Bypass translation cache read+write")
    ap.add_argument("--latest-day", action="store_true",
                    help="Translate only the most recent day's items (for the daily digest).")
    args = ap.parse_args(argv)

    try:
        doc = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"[err] bad JSON on stdin: {e}", file=sys.stderr)
        return 2

    n = sum(1 for it in doc.get("items", []) for f in _FIELDS
            if isinstance(it.get(f), str) and _needs_translation(it[f]))
    if n:
        print(f"[info] translating {n} zh fields via {args.model} ({args.host})", file=sys.stderr)
        doc = translate_doc(doc, args.host, args.model, use_cache=not args.no_cache,
                            latest_day_only=args.latest_day)
    json.dump(doc, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
