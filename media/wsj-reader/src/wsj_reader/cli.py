"""wsj CLI: headlines | article | audio. JSON to stdout, errors to stderr."""
from __future__ import annotations
import argparse
import json
import sys
from typing import Optional

from . import SCHEMA_VERSION
from .article import get_article
from .audio import get_audio
from .client import WSJError
from .headlines import get_headlines


def _emit(obj, *, json_errors: bool, error: Optional[WSJError] = None) -> int:
    if error is None:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
        return 0
    print(f"{error.code}: {error}", file=sys.stderr)
    if json_errors:
        print(json.dumps({"error": {"code": error.code, "message": str(error)}}))
    return error.exit_code


def _wrap(payload) -> dict:
    if isinstance(payload, dict) and "schema_version" in payload:
        return payload
    return {"schema_version": SCHEMA_VERSION, **(payload if isinstance(payload, dict) else {"value": payload})}


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="wsj", description="Read WSJ via the user's session.")

    def _common(sp):
        sp.add_argument("--json-errors", action="store_true",
                        help="Also emit structured {'error': ...} JSON on stdout when failing.")
        sp.add_argument("--no-cache", action="store_true")

    p.add_argument("--json-errors", action="store_true",
                   help="Accepted before the subcommand (same as the per-subcommand flag).")
    sub = p.add_subparsers(dest="cmd", required=True)

    ph = sub.add_parser("headlines", help="Print-edition headlines (cached 1h).")
    ph.add_argument("--date", help="Edition date as YYYYMMDD. Defaults to most recent.")
    ph.add_argument("--section", choices=["front", "business", "world", "popular"],
                    help="Restrict to a single section.")
    ph.add_argument("--limit", type=int, default=50, help="Max articles (0=all).")
    _common(ph)

    pa = sub.add_parser("article", help="Fetch one article by URL (cached 30d).")
    pa.add_argument("url", help="Full WSJ article URL.")
    _common(pa)

    pad = sub.add_parser("audio", help="Resolve and optionally download the MP3 for an article.")
    pad.add_argument("ref", help="WSJ article URL or bare WP-WSJ-* id.")
    pad.add_argument("--download", action="store_true", help="Also download the MP3 to cache.")
    _common(pad)

    args = p.parse_args(argv)

    try:
        if args.cmd == "headlines":
            payload = get_headlines(
                edition_date=args.date, section=args.section,
                limit=args.limit, no_cache=args.no_cache,
            )
        elif args.cmd == "article":
            payload = _wrap(get_article(args.url, no_cache=args.no_cache))
        elif args.cmd == "audio":
            payload = _wrap(get_audio(args.ref, download=args.download, no_cache=args.no_cache))
        else:
            p.error(f"unknown command {args.cmd}")
            return 1
    except WSJError as e:
        return _emit(None, json_errors=args.json_errors, error=e)

    return _emit(payload, json_errors=args.json_errors)


if __name__ == "__main__":
    sys.exit(main())
