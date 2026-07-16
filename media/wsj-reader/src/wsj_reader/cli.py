"""wsj CLI: headlines | article | audio. JSON to stdout, errors to stderr."""
from __future__ import annotations
import argparse
import sys
from typing import Optional

from news_reader_base import add_common_flags, emit, wrap

from . import SCHEMA_VERSION
from .article import get_article
from .audio import get_audio
from .client import WSJError
from .headlines import get_headlines


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="wsj", description="Read WSJ via the user's session.")
    p.add_argument("--json-errors", action="store_true",
                   help="Accepted before the subcommand (same as the per-subcommand flag).")
    sub = p.add_subparsers(dest="cmd", required=True)

    ph = sub.add_parser(
        "headlines",
        help=(
            "Headlines. Default transport is GraphQL (cookie required since "
            "mid-2026). Use --via=html for the print-edition scraper."
        ),
    )
    ph.add_argument(
        "--via", choices=["graphql", "html"], default="graphql",
        help="Transport: 'graphql' (default, cookie required) or 'html' (print edition).",
    )
    ph.add_argument(
        "--collection", default=None,
        help=(
            "GraphQL only: collection ID (e.g. MOST-POP-WSJ-NO-OPN_1) "
            "or alias (most-popular, most-popular-opinion, breaking). "
            "Defaults to most-popular."
        ),
    )
    ph.add_argument("--audio-only", action="store_true",
                    help="GraphQL only: drop articles without a narrated MP3.")
    ph.add_argument("--date", help="HTML only: edition date as YYYYMMDD. Defaults to most recent.")
    ph.add_argument("--section", choices=["front", "business", "world", "popular"],
                    help="HTML only: restrict to a single section.")
    ph.add_argument("--limit", type=int, default=50, help="Max articles (0=all).")
    add_common_flags(ph)

    pa = sub.add_parser("article", help="Fetch one article by URL (cached 30d).")
    pa.add_argument("url", help="Full WSJ article URL.")
    add_common_flags(pa)

    pad = sub.add_parser("audio", help="Resolve and optionally download the MP3 for an article.")
    pad.add_argument("ref", help="WSJ article URL or bare WP-WSJ-* id.")
    pad.add_argument("--download", action="store_true", help="Also download the MP3 to cache.")
    add_common_flags(pad)

    args = p.parse_args(argv)

    try:
        if args.cmd == "headlines":
            payload = get_headlines(
                via=args.via, collection=args.collection,
                audio_only=args.audio_only, edition_date=args.date,
                section=args.section, limit=args.limit, no_cache=args.no_cache,
            )
        elif args.cmd == "article":
            payload = wrap(get_article(args.url, no_cache=args.no_cache), SCHEMA_VERSION)
        elif args.cmd == "audio":
            payload = wrap(get_audio(args.ref, download=args.download, no_cache=args.no_cache), SCHEMA_VERSION)
        else:
            p.error(f"unknown command {args.cmd}")
            return 1
    except WSJError as e:
        return emit(None, json_errors=args.json_errors, error=e)

    return emit(payload, json_errors=args.json_errors)


if __name__ == "__main__":
    sys.exit(main())
