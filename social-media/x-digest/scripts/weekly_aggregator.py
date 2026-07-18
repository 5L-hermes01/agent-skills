#!/usr/bin/env python3
"""
Weekly aggregation script for X-digest pipeline.
Reads the last 7 daily cron output files for the ai-high-signal-digest job
and extracts prose + links from each for LLM synthesis.

Usage:
    python3 weekly_aggregator.py > /tmp/weekly_raw.txt

Output format per day:
    === YYYY-MM-DD ===
    [prose summary]

    Links (N):
    @handle: https://x.com/i/status/ID
    ...

Designed to be called from a weekly cron job. The LLM reads the output
and performs cross-week theme synthesis + link deduplication.
"""
import os
import re
import sys
from datetime import datetime, timezone, timedelta

CRON_OUTPUT_DIR = "/opt/data/cron/output/7c85dd238709"

def find_daily_files(num_days=7):
    """Find the most recent N daily cron output files."""
    if not os.path.isdir(CRON_OUTPUT_DIR):
        print(f"ERROR: Cron output dir not found: {CRON_OUTPUT_DIR}", file=sys.stderr)
        sys.exit(1)
    
    files = sorted(os.listdir(CRON_OUTPUT_DIR))
    
    # Build date -> path mapping from filenames like 2026-07-17_09-04-17.md
    found = {}
    for f in files:
        m = re.match(r"(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}-\d{2}\.md", f)
        if m:
            date_str = m.group(1)
            path = os.path.join(CRON_OUTPUT_DIR, f)
            # Keep the latest file per date
            found[date_str] = path
    
    # Get the most recent N dates
    sorted_dates = sorted(found.keys(), reverse=True)
    return {d: found[d] for d in sorted_dates[:num_days]}


def extract_prose_and_links(content):
    """Extract the Response prose and Links sections from a cron output file."""
    result = {"prose": "", "links": "", "link_count": 0}
    
    # Extract between "## Response" and "Links:" (or end)
    m = re.search(r"## Response\n\n(.+?)(?=\nLinks:|\n---|\Z)", content, re.DOTALL)
    if m:
        prose = m.group(1).strip()
        # Strip file-mutation verifier junk
        prose = re.sub(r"\n⚠️.*", "", prose, flags=re.DOTALL).strip()
        result["prose"] = prose
    
    # Extract links section
    m = re.search(r"^Links:\n(.+?)(?=\n⚠️|\Z)", content, re.DOTALL | re.MULTILINE)
    if m:
        links = m.group(1).strip()
        result["links"] = links
        result["link_count"] = len([l for l in links.split("\n") if l.strip() and l.startswith("@")])
    
    return result


def main():
    num_days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    daily_files = find_daily_files(num_days)
    
    if not daily_files:
        print("ERROR: No daily digest files found", file=sys.stderr)
        sys.exit(1)
    
    print(f"# X-Digest Weekly Summary — {list(daily_files.keys())[-1]} to {list(daily_files.keys())[0]}", file=sys.stderr)
    print(file=sys.stderr)
    
    for date_str in sorted(daily_files.keys()):
        path = daily_files[date_str]
        with open(path) as fh:
            content = fh.read()
        
        extracted = extract_prose_and_links(content)
        
        if extracted["prose"]:
            print(f"=== {date_str} ===")
            print(extracted["prose"])
            print()
        
        if extracted["links"]:
            print(f"Links ({extracted['link_count']}):")
            print(extracted["links"])
            print()
    
    # Summary stats to stderr
    total = sum(1 for d in daily_files if os.path.exists(daily_files[d]))
    with_prose = sum(1 for d in daily_files if extract_prose_and_links(open(daily_files[d]).read())["prose"])
    print(f"[aggregator] {total} files found, {with_prose} with prose content", file=sys.stderr)


if __name__ == "__main__":
    main()
