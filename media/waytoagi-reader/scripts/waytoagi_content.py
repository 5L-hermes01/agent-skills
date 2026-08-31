#!/usr/bin/env python3
"""Fetch and translate FULL article content for WaytoAGI digest items.

Reads flat WaytoAGI JSON (from `waytoagi update-log --flatten`) on stdin. For every
item with a Feishu `url`, this script:
  1. Fetches the article's guest-SSR HTML (cached by URL, long TTL).
  2. Renders the article body as text, PRESERVING external (non-Feishu) hyperlinks
     as markdown `[label](url)` — the reader's default render drops them.
  3. Batch-translates the full body to English via a local OpenAI-compatible
     endpoint (default qwen3.8), keeping the markdown link labels.
  4. Attaches `content_zh` / `content_en` to each item.
  5. Caches both raw article text and translation by URL so re-runs are instant.

Hyperlink policy: external (non-Feishu) links are preserved; internal Feishu doc
mentions are rendered as their title (text) since they're cross-refs within the wiki.

Usage:
    waytoagi update-log --flatten | waytoagi_content.py > out.json

Env:
    WAYTOAGI_TRANSLATE_HOST  default http://192.168.100.10:11434
    WAYTOAGI_TRANSLATE_MODEL default qwen3.8
    WAYTOAGI_CONTENT_CACHE   default $XDG_CACHE_HOME/waytoagi-content
    WAYTOAGI_BATCH_CHARS     default 2000 (zh chars per translation batch)
    WAYTOAGI_MAX_ARTICLES    default 0 = unlimited
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_SYSTEM_PROMPT = (
    "You are a precise Chinese-to-English translator. Translate the full article "
    "faithfully. Keep every markdown hyperlink intact exactly as written, e.g. "
    "[label](url). Preserve product names, numbers, and URLs. Return only the "
    "translated text."
)

_ZH_RE = re.compile(r"[\u4e00-\u9fff]")
_FEISHU_HOSTS = ("waytoagi.feishu.cn", "feishu.cn", "larksuite.com")
# attrib run regex — same as reader's blocks.py
_RUN_RE = re.compile(r"((?:\*[0-9a-z]+)+)\+([0-9a-z]+)")


# ── block rendering with hyperlink preservation ────────────────────────────

def render_content_runs(b):
    """Like blocks.render_runs but ALSO emits external `link` attribs as
    {'type':'link','url':...,'label':chunk}. Internal Feishu mentions render as
    their title (plain text)."""
    data = b.get("data") or {}
    t = data.get("text")
    if not isinstance(t, dict):
        return []
    apool = (t.get("apool") or {}).get("numToAttrib") or {}
    iat = t.get("initialAttributedTexts") or {}
    attribs = (iat.get("attribs") or {}).get("0", "")
    raw = (iat.get("text") or {}).get("0", "")
    out = []
    pos = 0
    for m in _RUN_RE.finditer(attribs):
        keys = re.findall(r"\*([0-9a-z]+)", m.group(1))
        length = int(m.group(2), 36)
        chunk = raw[pos:pos + length]
        pos += length
        link_url = None
        mention_title = None
        for k in keys:
            attrib = apool.get(k)
            if not attrib:
                continue
            kind = attrib[0]
            val = attrib[1] if len(attrib) > 1 else None
            if kind == "link" and isinstance(val, str):
                link_url = val
            elif kind == "inline-component" and val:
                try:
                    comp = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    comp = None
                if comp and comp.get("type") == "mention_doc":
                    mention_title = ((comp.get("data") or {}).get("title") or "").strip()
        if link_url and not _is_feishu(link_url):
            out.append({"type": "link", "url": link_url, "label": chunk})
        elif mention_title:
            out.append(mention_title)
        else:
            out.append(chunk)
    if pos < len(raw):
        out.append(raw[pos:])
    return out


def _is_feishu(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == h or host.endswith("." + h) for h in _FEISHU_HOSTS)


def render_article_text(b):
    """Render a text/bullet block to a string with external links as [label](url)."""
    parts = []
    for p in render_content_runs(b):
        if isinstance(p, dict) and p.get("type") == "link":
            label = (p.get("label") or p.get("url") or "").strip()
            parts.append(f"[{label}]({p['url']})" if label else p["url"])
        elif isinstance(p, dict):
            parts.append(str(p.get("label") or ""))
        else:
            parts.append(str(p))
    return "".join(parts).strip()


# ── article fetch + render ─────────────────────────────────────────────────

def fetch_blocks(url: str):
    """Fetch + extract blocks for one article (cached by URL). Returns dict."""
    sys.path.insert(0, "/opt/data/repos/agent-skills/media/waytoagi-reader/src")
    from waytoagi_reader.cache import cached_fetch
    from waytoagi_reader.client import fetch_html
    from waytoagi_reader.bootstrap import extract_blocks
    res = cached_fetch(url, fetcher=fetch_html, mode="read+write", ttl=7 * 24 * 3600)
    return extract_blocks(res.body)


def render_page_body(blocks: dict) -> str:
    """Render the page's content blocks in order. Drop the page root block itself."""
    page_id = None
    for bid, b in blocks.items():
        if (b.get("data") or {}).get("type") == "page":
            page_id = bid
            break
    if not page_id:
        return ""
    order = (blocks[page_id].get("data") or {}).get("children") or []
    # walk depth-first, collecting text/bullet/quote/heading blocks
    out = []
    seen = set()

    def walk(cid, depth=0):
        if cid in seen or cid not in blocks:
            return
        seen.add(cid)
        b = blocks[cid]
        d = b.get("data") or {}
        bt = d.get("type")
        if bt in ("text", "bullet", "quote", "heading1", "heading2", "heading3"):
            s = render_article_text(b)
            if s:
                out.append(s)
        for kid in (d.get("children") or []):
            walk(kid, depth + 1)

    for cid in order:
        walk(cid)
    return "\n".join(out)


# ── translation (reuse batch logic, char-budget batching) ─────────────────

def _needs_translation(s: str) -> bool:
    return bool(s) and len(s) >= 2 and bool(_ZH_RE.search(s))


def _batch_chars() -> int:
    return int(os.environ.get("WAYTOAGI_BATCH_CHARS", "2000"))


def _post(host, model, lines, timeout):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "Translate to English:\n\n" + "\n".join(lines)},
        ],
        "temperature": 0.1,
        "max_tokens": 4000,
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


def _translate_text(host, model, text):
    """Translate one article body, splitting into char-budget chunks to fit
    the model's output window. Returns English string."""
    if not _needs_translation(text):
        return text
    batch_chars = _batch_chars()
    # split into paragraphs, group by budget
    chunks = []
    cur = []
    cur_len = 0
    for para in text.split("\n\n"):
        pl = len(para)
        if cur and cur_len + pl > batch_chars:
            chunks.append("\n\n".join(cur))
            cur, cur_len = [], 0
        cur.append(para)
        cur_len += pl
    if cur:
        chunks.append("\n\n".join(cur))
    out = []
    for c in chunks:
        lines = [f"[0] {c}"]
        ok = False
        for attempt in range(3):
            try:
                raw = _post(host, model, lines, timeout=300)
                # strip a leading [0] marker if present, keep the whole body
                m = re.search(r"^\s*\[0\]\s*(.+)$", raw, re.MULTILINE | re.DOTALL)
                out.append((m.group(1).strip() if m else raw.strip()))
                ok = True
                break
            except Exception as e:
                print(f"[warn] content chunk attempt {attempt+1} failed: {e}", file=sys.stderr)
                time.sleep(1.0 * (attempt + 1))
        if not ok:
            out.append("")  # mark failure; caller can fall back to summary
    return "\n\n".join(x for x in out if x)


def _content_cache_dir() -> Path:
    base = os.environ.get("WAYTOAGI_CONTENT_CACHE")
    if base:
        return Path(base)
    xdg = os.environ.get("XDG_CACHE_HOME")
    root = Path(xdg) if xdg else Path.home() / ".cache"
    return root / "waytoagi-content"


def _content_cache_path(url: str, lang: str) -> Path:
    import hashlib
    key = hashlib.sha256(url.encode()).hexdigest()
    return _content_cache_dir() / lang / f"{key}.txt"


def _cache_get(url, lang):
    p = _content_cache_path(url, lang)
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


def _cache_put(url, lang, text):
    p = _content_cache_path(url, lang)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


# ── main ───────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=os.environ.get("WAYTOAGI_TRANSLATE_HOST", "http://192.168.100.10:11434"))
    ap.add_argument("--model", default=os.environ.get("WAYTOAGI_TRANSLATE_MODEL", "qwen3.8"))
    ap.add_argument("--no-cache", action="store_true", help="Bypass content + translation cache")
    ap.add_argument("--batch-chars", type=int, default=None,
                    help="Max source chars per translation batch (default env WAYTOAGI_BATCH_CHARS or 2000).")
    ap.add_argument("--limit", type=int, default=0,
                    help="Max articles to fetch+translate (0 = all). Useful for dry runs.")
    args = ap.parse_args(argv)

    if args.batch_chars:
        os.environ["WAYTOAGI_BATCH_CHARS"] = str(args.batch_chars)

    try:
        doc = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"[err] bad JSON on stdin: {e}", file=sys.stderr)
        return 2

    items = doc.get("items", [])
    fetched = 0
    for it in items:
        url = it.get("url")
        if not url:
            continue
        if args.limit and fetched >= args.limit:
            break
        # content already present?
        if it.get("content_en"):
            continue
        try:
            zh = _cache_get(url, "zh") if not args.no_cache else None
            en = _cache_get(url, "en") if not args.no_cache else None
            if zh is None:
                blocks = fetch_blocks(url)
                zh = render_page_body(blocks)
                if not args.no_cache and zh:
                    _cache_put(url, "zh", zh)
            if en is None and zh:
                en = _translate_text(args.host, args.model, zh)
                if not args.no_cache and en:
                    _cache_put(url, "en", en)
            if zh:
                it["content_zh"] = zh
            if en:
                it["content_en"] = en
            fetched += 1
            print(f"[info] fetched+translated {url} ({len(zh or '')}zh chars -> {len(en or '')}en)", file=sys.stderr)
        except Exception as e:
            print(f"[warn] content failed for {url}: {type(e).__name__}: {e}", file=sys.stderr)

    json.dump(doc, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
