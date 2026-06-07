"""ft CLI: headlines | article | audio | myft. JSON to stdout, errors to stderr."""
from __future__ import annotations
import argparse
import json
import sys
from typing import Optional

from . import SCHEMA_VERSION
from .article import get_article
from .audio import get_audio
from .client import FTError, SessionExpiredError
from .headlines import get_headlines
from .myft import get_myft


def _emit(obj, *, json_errors: bool, error: Optional[FTError] = None) -> int:
    if error is None:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
        return 0
    msg = f"{error.code}: {error}"
    print(msg, file=sys.stderr)
    if json_errors:
        print(json.dumps({"error": {"code": error.code, "message": str(error)}}))
    return error.exit_code


def _wrap(payload) -> dict:
    if isinstance(payload, dict) and "schema_version" in payload:
        return payload
    return {"schema_version": SCHEMA_VERSION, **(payload if isinstance(payload, dict) else {"value": payload})}


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="ft", description="Read FT.com via the user's session.")

    def _common(sp):
        sp.add_argument("--json-errors", action="store_true",
                        help="Also emit structured {'error': ...} JSON on stdout when failing.")
        sp.add_argument("--no-cache", action="store_true")

    p.add_argument("--json-errors", action="store_true",
                   help="Same as the per-subcommand flag; accepted before the subcommand.")
    sub = p.add_subparsers(dest="cmd", required=True)

    ph = sub.add_parser("headlines", help="Top headlines per section (cached 1h + 30d per article).")
    ph.add_argument("--section", help="Restrict to one section id (e.g. world, tech, lex).")
    ph.add_argument("--limit", type=int, default=5, help="Headlines per section (default 5).")
    _common(ph)

    pa = sub.add_parser("article", help="Fetch one article by UUID or URL (cached 30d).")
    pa.add_argument("ref", help="Article UUID or full FT URL.")
    _common(pa)

    pad = sub.add_parser("audio", help="Resolve and optionally download the MP3 for an article.")
    pad.add_argument("ref", help="Article UUID or full FT URL.")
    pad.add_argument("--download", action="store_true", help="Also download the MP3 to cache.")
    _common(pad)

    pm = sub.add_parser("myft", help="List saved (MyFT) articles. Optionally download all available MP3s.")
    pm.add_argument("--limit", type=int, default=50)
    pm.add_argument("--download-audio", action="store_true")
    _common(pm)

    args = p.parse_args(argv)

    try:
        if args.cmd == "headlines":
            payload = get_headlines(section=args.section, limit=args.limit, no_cache=args.no_cache)
        elif args.cmd == "article":
            payload = _wrap(get_article(args.ref, no_cache=args.no_cache))
        elif args.cmd == "audio":
            payload = _wrap(get_audio(args.ref, download=args.download, no_cache=args.no_cache))
        elif args.cmd == "myft":
            payload = get_myft(limit=args.limit, download_audio=args.download_audio,
                               no_cache=args.no_cache)
        else:
            p.error(f"unknown command {args.cmd}")
            return 1
    except FTError as e:
        return _emit(None, json_errors=args.json_errors, error=e)

    return _emit(payload, json_errors=args.json_errors)


if __name__ == "__main__":
    sys.exit(main())
