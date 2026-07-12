#!/usr/bin/env python3
"""
WaytoAGI Weekly Recap — POC

Fetches the WaytoAGI Feishu wiki daily update log and formats
a weekly recap digest for delivery to the weekly-ai Discord channel.

Usage:
    python3 /opt/data/scripts/waytoagi-weekly-recap.py
    python3 /opt/data/scripts/waytoagi-weekly-recap.py --deliver

Output: formatted digest to stdout.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ── Path Setup ─────────────────────────────────────────────────────────────

# Ensure waytoagi-reader is importable in cron environment
_SKILL_REPO = os.path.expanduser("/opt/data/repos/agent-skills")
for _p in ["media/waytoagi-reader/src"]:
    _path = os.path.join(_SKILL_REPO, _p)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from waytoagi_reader.cli import main as waytoagi_main

# ── Configuration ──────────────────────────────────────────────────────────

# Translation — llama.cpp server (OpenAI-compatible)
LLAMA_CPP_HOST = "http://lunarbeacon.newyork.nicklange.family:11434"
LLAMA_CPP_MODEL = "gemma-4-26b-a4b-it-qat"

CACHE_DIR = os.path.expanduser("~/.cache/waytoagi-reader")


# ── Translation ─────────────────────────────────────────────────────────────

_TRANSLATION_CACHE: dict[str, str] = {}
_TRANSLATION_AVAILABLE: bool | None = None  # None=untested, True/False=cached


def _check_translation_available() -> bool:
    """Quick liveness check via proper HTTP request to /v1/models."""
    global _TRANSLATION_AVAILABLE
    if _TRANSLATION_AVAILABLE is not None:
        return _TRANSLATION_AVAILABLE
    try:
        url = f"{LLAMA_CPP_HOST}/v1/models"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            _TRANSLATION_AVAILABLE = resp.status == 200
        if not _TRANSLATION_AVAILABLE:
            print(f"[info] Translation backend returned non-200, skipping translation", file=sys.stderr)
        return _TRANSLATION_AVAILABLE
    except Exception as e:
        print(f"[info] Translation backend unreachable ({e}), skipping translation", file=sys.stderr)
        _TRANSLATION_AVAILABLE = False
        return False


def translate_text(text: str, target: str = "en", source: str = "auto") -> str:
    """Translate text via llama.cpp OpenAI-compatible endpoint."""
    if not text or len(text) < 3:
        return text
    cache_key = f"{source}:{target}:{text}"
    if cache_key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[cache_key]
    result = _batch_translate([text], target, source)[0]
    _TRANSLATION_CACHE[cache_key] = result
    return result


def _batch_translate(texts: list[str], target: str = "en", source: str = "auto") -> list[str]:
    """Translate multiple texts in a single API call. Splits into chunks for reliability."""
    if not texts:
        return []

    # Filter to texts that actually need translation (have Chinese chars)
    needs_translation = [(i, t) for i, t in enumerate(texts) if t and len(t) >= 3 and re.search(r"[\u4e00-\u9fff]", t)]
    if not needs_translation:
        return texts[:]

    # Split into chunks of 10 for model's latency limits
    chunk_size = 10
    results = list(texts)

    for chunk_start in range(0, len(needs_translation), chunk_size):
        chunk = needs_translation[chunk_start:chunk_start + chunk_size]
        lines = [f"[{idx}] {t}" for idx, t in chunk]

        prompt = "Translate to English:\n\n" + "\n".join(lines)

        payload = {
            "model": LLAMA_CPP_MODEL,
            "messages": [
                {"role": "system", "content": "You are a precise Chinese-to-English translator. Translate each numbered item. Return only the numbered translations."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "stream": False,
        }

        url = f"{LLAMA_CPP_HOST}/v1/chat/completions"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
            result_raw = (body.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()

            # Parse numbered results back
            translations: dict[int, str] = {}
            for match in re.finditer(r"^\[(\d+)\]\s*(.+)$", result_raw, re.MULTILINE):
                idx = int(match.group(1))
                text_val = match.group(2).strip()
                translations[idx] = text_val

            for idx, t in chunk:
                if idx in translations and translations[idx]:
                    results[idx] = translations[idx]
        except Exception as e:
            print(f"[warn] Batch chunk failed ({e}), trying per-item for this chunk", file=sys.stderr)
            for idx, t in chunk:
                try:
                    single_payload = {
                        "model": LLAMA_CPP_MODEL,
                        "messages": [
                            {"role": "system", "content": "You are a precise Chinese-to-English translator. Return only the translation."},
                            {"role": "user", "content": f"Translate to English:\n{t}"},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 500,
                        "stream": False,
                    }
                    single_req = urllib.request.Request(
                        url,
                        data=json.dumps(single_payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(single_req, timeout=30) as resp:
                        single_body = json.loads(resp.read())
                    result = (single_body.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
                    if result:
                        results[idx] = result
                except Exception:
                    pass

    return results


def _translate_items(items: list[dict]) -> None:
    """Batch-translate all Chinese titles and summaries in items list, in-place."""
    # Collect all texts that need translation
    title_texts = []
    summary_texts = []
    title_indices = []
    summary_indices = []

    for i, item in enumerate(items):
        title = item.get("title", "")
        summary = item.get("summary", "")
        if title and re.search(r"[\u4e00-\u9fff]", title):
            title_indices.append(i)
            title_texts.append(title)
        if summary and re.search(r"[\u4e00-\u9fff]", summary):
            summary_indices.append(i)
            summary_texts.append(summary)

    if title_texts:
        print(f"[info] Translating {len(title_texts)} titles...", file=sys.stderr)
        translated = _batch_translate(title_texts)
        for idx, trans in zip(title_indices, translated):
            items[idx]["title_en"] = trans

    if summary_texts:
        print(f"[info] Translating {len(summary_texts)} summaries...", file=sys.stderr)
        translated = _batch_translate(summary_texts)
        for idx, trans in zip(summary_indices, translated):
            items[idx]["summary_en"] = trans


# ── Helpers ────────────────────────────────────────────────────────────────


def fetch_waytoagi(no_cache: bool = False) -> dict:
    """Fetch WaytoAGI update log via direct module call (no subprocess)."""
    argv = ["update-log", "--flatten"]
    if no_cache:
        argv.append("--no-cache")

    # Capture stdout from the CLI
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exit_code = waytoagi_main(argv)

    stdout = buf.getvalue()
    if exit_code != 0:
        print(f"[err] waytoagi update-log failed (exit={exit_code})",
              file=sys.stderr)
        return {}

    # Parse JSON from stdout (stderr has info messages)
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        print(f"[err] JSON parse: {e}", file=sys.stderr)
        print(f"[debug] stdout starts: {stdout[:200]}", file=sys.stderr)
        return {}


def group_items_by_day(items: list[dict]) -> list[dict]:
    """Group flat items back into day buckets, preserving order."""
    days_map: dict[str, list[dict]] = {}
    day_order: list[str] = []
    for item in items:
        day = item.get("day", "")
        if day and day not in days_map:
            days_map[day] = []
            day_order.append(day)
        if day:
            days_map[day].append(item)
    return [{"heading": d, "items": days_map[d]} for d in day_order]


def format_week_recap(data: dict, translate: bool = False) -> str:
    """Format WaytoAGI data into a weekly recap digest."""
    items = data.get("items", [])
    if not items:
        return "[WaytoAGI Weekly Recap] No updates found."

    source_url = data.get("source_url", "")
    stats = {"translated": 0, "total_text_items": 0}

    # Batch-translate all items upfront if translation is enabled
    if translate:
        _translate_items(items)
        # Also cache individual translations for the per-item path's convenience
        for item in items:
            if item.get("title_en"):
                _TRANSLATION_CACHE[f"auto:en:{item.get('title','')}"] = item["title_en"]
            if item.get("summary_en"):
                _TRANSLATION_CACHE[f"auto:en:{item.get('summary','')}"] = item["summary_en"]

    # Group by day
    days = group_items_by_day(items)

    lines = []
    lines.append("WaytoAGI Weekly Recap")
    lines.append(f"Source: {source_url}")
    if translate:
        lines.append("(Chinese summaries translated to English)")
    lines.append("")

    total_items = 0
    for day in days:
        heading = day["heading"]
        day_items = day["items"]
        if not heading:
            continue
        total_items += len(day_items)

        lines.append(f"[ {heading} ]")
        lines.append("")

        for item in day_items:
            title = item.get("title") or "(untitled)"
            summary = item.get("summary") or ""
            url = item.get("url") or ""
            item_type = item.get("type", "")

            if item_type == "image":
                continue  # Skip image-only entries

            stats["total_text_items"] += 1
            if translate:
                title_en = item.get("title_en", "")
                if re.search(r"[\u4e00-\u9fff]", title) and title_en:
                    stats["translated"] += 1
                    lines.append(f"  {title}")
                    lines.append(f"  EN: {title_en}")
                else:
                    lines.append(f"  {title}")

                if summary:
                    summary_en = item.get("summary_en", "")
                    if re.search(r"[\u4e00-\u9fff]", summary) and summary_en:
                        s = summary_en.replace("\n", " ").strip()
                        if len(s) > 250:
                            s = s[:247] + "..."
                        lines.append(f"    {s}")
                    else:
                        s = summary.replace("\n", " ").strip()
                        if len(s) > 200:
                            s = s[:197] + "..."
                        lines.append(f"    {s}")
            else:
                lines.append(f"  {title}")
                if summary:
                    s = summary.replace("\n", " ").strip()
                    if len(s) > 200:
                        s = s[:197] + "..."
                    lines.append(f"    {s}")

            if url:
                lines.append(f"    {url}")
            lines.append("")

    lines.append(f"---")
    lines.append(f"{len(days)} days, {total_items} items")
    if translate:
        lines.append(f"{stats['translated']}/{stats['total_text_items']} items translated")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="WaytoAGI Weekly Recap")
    ap.add_argument("--no-cache", action="store_true", help="Bypass cache")
    ap.add_argument("--no-translate", action="store_true",
                    help="Skip Chinese-to-English translation")
    ap.add_argument("--deliver", action="store_true",
                    help="Also write to delivery file for Discord")
    args = ap.parse_args()

    print("[info] Fetching WaytoAGI update log...", file=sys.stderr)
    data = fetch_waytoagi(no_cache=args.no_cache)
    if not data:
        print("[err] Failed to fetch WaytoAGI data", file=sys.stderr)
        return 1

    items = data.get("items", [])
    print(f"[info] Fetched {len(items)} flat items", file=sys.stderr)

    # Count by type
    types = {}
    for item in items:
        t = item.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
    print(f"[info] Item types: {types}", file=sys.stderr)

    # Quick liveness check before attempting translations
    do_translate = not args.no_translate
    if do_translate:
        if _check_translation_available():
            print("[info] Translation backend available, enabling", file=sys.stderr)
        else:
            print("[info] Translation backend unavailable, falling back to Chinese", file=sys.stderr)
            do_translate = False

    recap = format_week_recap(data, translate=do_translate)
    print(recap)

    if args.deliver:
        out_dir = os.path.expanduser("~/.hermes/cron/output/waytoagi-weekly")
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d")
        out_path = os.path.join(out_dir, f"recap-{ts}.txt")
        with open(out_path, "w") as f:
            f.write(recap)
        print(f"[info] Saved to {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
