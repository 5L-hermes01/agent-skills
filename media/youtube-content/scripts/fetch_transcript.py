#!/usr/bin/env python3
"""
Fetch a YouTube video transcript and output it as structured JSON.
Auto-saves raw transcript data to file for future re-formatting.

Usage:
    python fetch_transcript.py <url_or_video_id> [--language en,tr] [--timestamps]
                         [--save-dir DIR] [--no-save]

Output (JSON):
    {
        "video_id": "...",
        "language": "en",
        "segments": [{"text": "...", "start": 0.0, "duration": 2.5}, ...],
        "full_text": "complete transcript as plain text",
        "timestamped_text": "00:00 first line\n00:05 second line\n..."
    }

Auto-saves:
    - {save_dir}/{video_id}.json        (full transcript data with segments)
    - {save_dir}/{video_id}_timestamped.txt  (timestamped plain text)

Install dependency:  pip install youtube-transcript-api
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


def extract_video_id(url_or_id: str) -> str:
    """Extract the 11-character video ID from various YouTube URL formats."""
    url_or_id = url_or_id.strip()
    patterns = [
        r'(?:v=|youtu\.be/|shorts/|embed/|live/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return url_or_id


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fetch_transcript(video_id: str, languages: list = None):
    """Fetch transcript segments from YouTube.

    Returns a list of dicts with 'text', 'start', and 'duration' keys.
    Compatible with youtube-transcript-api v1.x.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("Error: youtube-transcript-api not installed. Run: pip install youtube-transcript-api",
              file=sys.stderr)
        sys.exit(1)

    api = YouTubeTranscriptApi()
    if languages:
        result = api.fetch(video_id, languages=languages)
    else:
        result = api.fetch(video_id)

    # v1.x returns FetchedTranscriptSnippet objects; normalize to dicts
    return [
        {"text": seg.text, "start": seg.start, "duration": seg.duration}
        for seg in result
    ]


def save_transcript_files(video_id: str, segments: list, save_dir: Path):
    """Save raw transcript data and timestamped text to files."""
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    full_text = " ".join(seg["text"] for seg in segments)
    timestamped = "\n".join(
        f"{format_timestamp(seg['start'])} {seg['text']}" for seg in segments
    )

    # Build JSON data
    json_data = {
        "video_id": video_id,
        "language": "auto",
        "segment_count": len(segments),
        "duration": format_timestamp(segments[-1]["start"] + segments[-1]["duration"]) if segments else "0:00",
        "segments": segments,
        "full_text": full_text,
    }

    # Save JSON with full transcript data
    json_path = save_dir / f"{video_id}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    # Save timestamped plain text
    txt_path = save_dir / f"{video_id}_timestamped.txt"
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(timestamped)

    return json_path, txt_path


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube transcript as JSON")
    parser.add_argument("url", help="YouTube URL or video ID")
    parser.add_argument("--language", "-l", default=None,
                        help="Comma-separated language codes (e.g. en,tr). Default: auto")
    parser.add_argument("--timestamps", "-t", action="store_true",
                        help="Include timestamped text in output")
    parser.add_argument("--text-only", action="store_true",
                        help="Output plain text instead of JSON")
    parser.add_argument("--save-dir", "-s", default=None,
                        help="Directory to save raw transcript files. If not set, no files are saved.")
    parser.add_argument("--no-save", action="store_true",
                        help="Explicitly disable file saving (even if SAVE_DIR env var is set)")
    args = parser.parse_args()

    video_id = extract_video_id(args.url)
    languages = [l.strip() for l in args.language.split(",")] if args.language else None

    try:
        segments = fetch_transcript(video_id, languages)
    except Exception as e:
        error_msg = str(e)
        if "disabled" in error_msg.lower():
            print(json.dumps({"error": "Transcripts are disabled for this video."}))
        elif "no transcript" in error_msg.lower():
            print(json.dumps({"error": f"No transcript found. Try specifying a language with --language."}))
        else:
            print(json.dumps({"error": error_msg}))
        sys.exit(1)

    full_text = " ".join(seg["text"] for seg in segments)
    timestamped = "\n".join(
        f"{format_timestamp(seg['start'])} {seg['text']}" for seg in segments
    )

    # Save files if requested (or via env var)
    save_dir = None
    if not args.no_save:
        if args.save_dir:
            save_dir = Path(args.save_dir)
        elif os.environ.get("SAVE_DIR"):
            save_dir = Path(os.environ["SAVE_DIR"])

    if save_dir:
        json_path, txt_path = save_transcript_files(video_id, segments, save_dir)
        print(f"[Saved: {json_path}, {txt_path}]", file=sys.stderr)

    if args.text_only:
        print(timestamped if args.timestamps else full_text)
        return

    result = {
        "video_id": video_id,
        "segment_count": len(segments),
        "duration": format_timestamp(segments[-1]["start"] + segments[-1]["duration"]) if segments else "0:00",
        "full_text": full_text,
    }
    if args.timestamps:
        result["timestamped_text"] = timestamped

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
