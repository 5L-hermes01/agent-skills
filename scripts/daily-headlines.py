#!/usr/bin/env python3
"""Daily headlines: FT + WSJ + NYT combined, deduplicated, top 15."""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _run(cmd: list[str], *, timeout: int = 45, pythonpath: str = "") -> tuple[list[dict] | None, str]:
    """Run a headlines command, return (articles list or None, failure_reason)."""
    env = None
    if pythonpath:
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{pythonpath}:{existing}" if existing else pythonpath
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"
    except FileNotFoundError as e:
        return None, f"command not found: {e}"
    if r.returncode != 0:
        reason = r.stderr.strip()[:200] or "(no stderr)"
        return None, f"exit {r.returncode}: {reason}"
    try:
        payload = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None, f"non-JSON output (got {len(r.stdout)} chars)"
    result = payload.get("articles") or payload.get("sections", [])
    if not result:
        return None, "empty result set"
    return result, ""


def normalize_title(title: str) -> str:
    """Normalize title for deduplication (lowercase, alphanumeric only)."""
    return re.sub(r'[^a-z0-9]', '', title.lower())


def _has_env(path: Path) -> bool:
    env = path / ".env"
    return env.exists() and env.read_text().strip() != ""


def main() -> tuple[str, int]:
    lines: list[str] = []
    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    lines.append(f"Daily Headlines — {today}")
    lines.append("")

    all_stories: dict[str, dict] = {}
    news_base_dir = Path("/opt/data/repos/agent-skills/media/news-reader-base/src")
    sources_attempted = 0
    sources_failed = 0

    # ── WSJ (GraphQL — needs cookie + ascii-sanitized) ──
    wsj_dir = Path("/opt/data/repos/agent-skills/media/wsj-reader")
    if (wsj_dir / "src").exists():
        sources_attempted += 1
        wsj_pypath = f"{wsj_dir / 'src'}:{news_base_dir}"
        arts, reason = _run([
            sys.executable, "-m", "wsj_reader.cli", "headlines", "--limit", "15",
        ], timeout=45, pythonpath=wsj_pypath)
        if arts:
            for a in arts:
                title = a.get("headline") or a.get("title") or ""
                if not title:
                    continue
                norm = normalize_title(title)
                if norm not in all_stories:
                    all_stories[norm] = {"title": title, "sources": {}, "standfirst": a.get("standfirst", "")}
                all_stories[norm]["sources"]["WSJ"] = a.get("url", "")
        else:
            sources_failed += 1
            lines.append(f"[WSJ: failed — {reason}]")

    # ── FT (needs cookie) ──
    ft_dir = Path("/opt/data/skills/media/ft-reader")
    if _has_env(ft_dir) and (ft_dir / "src").exists():
        sources_attempted += 1
        ft_pypath = f"{ft_dir / 'src'}:{news_base_dir}"
        arts, reason = _run([
            sys.executable, "-m", "ft_reader.cli", "headlines",
        ], timeout=180, pythonpath=ft_pypath)
        if arts:
            for section_blob in arts:
                for h in section_blob.get("headlines", []):
                    title = h.get("title") or h.get("headline", "")
                    if not title:
                        continue
                    norm = normalize_title(title)
                    if norm not in all_stories:
                        all_stories[norm] = {"title": title, "sources": {}, "standfirst": h.get("standfirst", "")}
                    all_stories[norm]["sources"]["FT"] = h.get("url", "")
        else:
            sources_failed += 1
            lines.append(f"[FT: failed — {reason}]")

    # ── NYT (needs 5 cookies) ──
    nyt_dir = Path("/opt/data/repos/agent-skills/media/nyt-reader")
    if _has_env(nyt_dir) and (nyt_dir / "src").exists():
        sources_attempted += 1
        nyt_pypath = f"{nyt_dir / 'src'}:{news_base_dir}"
        arts, reason = _run([
            sys.executable, "-m", "nyt_reader.cli", "headlines", "--limit", "15",
        ], timeout=45, pythonpath=nyt_pypath)
        if arts:
            for a in arts:
                title = a.get("headline") or a.get("title") or ""
                if not title:
                    continue
                norm = normalize_title(title)
                if norm not in all_stories:
                    all_stories[norm] = {"title": title, "sources": {}, "standfirst": a.get("standfirst", "")}
                all_stories[norm]["sources"]["NYT"] = a.get("url", "")
        else:
            sources_failed += 1
            lines.append(f"[NYT: failed — {reason}]")

    # If every attempted source failed, exit non-zero so the cron job marks as error.
    all_failed = sources_attempted > 0 and sources_failed == sources_attempted

    # Select top 15 stories with source diversity:
    # 1. Stories covered by multiple sources come first (sorted by source count desc)
    # 2. Remaining slots filled by round-robin across sources (sorted by title desc within source)
    multi = sorted(
        (s for s in all_stories.values() if len(s["sources"]) > 1),
        key=lambda x: len(x["sources"]), reverse=True
    )
    single = {src: [] for src in ("FT", "WSJ", "NYT")}
    for s in all_stories.values():
        if len(s["sources"]) == 1:
            src = next(iter(s["sources"]))
            if src in single:
                single[src].append(s)
    for src in single:
        single[src].sort(key=lambda x: x["title"], reverse=True)

    sorted_stories = list(multi)
    src_order = ["FT", "WSJ", "NYT"]
    idx = {src: 0 for src in src_order}
    while len(sorted_stories) < 15:
        added = False
        for src in src_order:
            if idx[src] < len(single[src]):
                cand = single[src][idx[src]]
                idx[src] += 1
                if cand not in sorted_stories:
                    sorted_stories.append(cand)
                    added = True
                    if len(sorted_stories) >= 15:
                        break
        if not added:
            break  # no more stories from any source

    for i, story in enumerate(sorted_stories, 1):
        sources = " ".join(
            f"[{src}] {url}" if url else f"[{src}]"
            for src, url in sorted(story["sources"].items())
        )
        lines.append(f"{i}. {story['title']} {sources}")
        if story["standfirst"]:
            lines.append(f"   {story['standfirst']}")

    if len(lines) <= 2:
        output = ""  # silent — nothing to report
    else:
        output = "\n".join(lines)
    exit_code = 1 if (all_failed or (len(lines) <= 2 and sources_attempted > 0 and not all_stories)) else 0
    return output, exit_code


if __name__ == "__main__":
    output, exit_code = main()
    if output:
        print(output)
    sys.exit(exit_code)
