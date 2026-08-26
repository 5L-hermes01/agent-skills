#!/usr/bin/env python3
"""Fetch the last 7 days of smol.ai news issues and extract full content."""
import urllib.request
import re
import sys
from datetime import datetime, timedelta

def get_weekly_news():
    url = "https://news.smol.ai/rss.xml"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        response = urllib.request.urlopen(req)
        xml_data = response.read()
    except Exception as e:
        print(f"Error fetching feed: {e}", file=sys.stderr)
        return

    content = xml_data.decode('utf-8', errors='replace')
    items = list(re.finditer(r'<item>(.*?)</item>', content, re.DOTALL))
    if not items:
        print("No news found.")
        return

    # Parse all items with dates
    parsed = []
    for item_match in items:
        item = item_match.group(1)
        title_m = re.search(r'<title>(.*?)</title>', item)
        link_m = re.search(r'<link>(.*?)</link>', item)
        date_m = re.search(r'<pubDate>(.*?)</pubDate>', item)
        title = title_m.group(1) if title_m else "Unknown"
        link = link_m.group(1) if link_m else "https://news.smol.ai/"
        pubDate = date_m.group(1) if date_m else ""
        parsed.append((title, link, pubDate))

    cutoff = datetime.now() - timedelta(days=7)
    recent = []
    for title, link, pubDate in parsed:
        # smol.ai dates are like "Mon, 09 Jun 2026 00:00:00 +0000"
        try:
            # Handle both "GMT" and "+0000" timezone formats
            cleaned = pubDate
            if cleaned.endswith('GMT'):
                cleaned = cleaned[:-3].strip()
            if '+' in cleaned:
                cleaned = cleaned.split('+')[0].strip()
            dt = datetime.strptime(cleaned, "%a, %d %b %Y %H:%M:%S")
            if dt >= cutoff:
                recent.append((title, link, pubDate))
        except Exception as e:
            print(f"Date parse error for '{title}': {e}", file=sys.stderr)
            # On genuine parse failure, include the item rather than drop it
            try:
                dt = datetime.strptime(cleaned, "%a, %d %b %Y %H:%M:%S")
                if dt >= cutoff:
                    recent.append((title, link, pubDate))
            except:
                pass

    print(f"=== WEEKLY AI NEWS ({len(recent)} items, past 7 days) ===\n")
    print(f"Period: {datetime.now().strftime('%Y-%m-%d')} (trailing 7 days)\n")

    for title, link, pubDate in recent:
        print(f"--- {title} ---")
        print(f"Published: {pubDate}")
        print(f"URL: {link}\n")
        try:
            jina_url = "https://r.jina.ai/" + link
            jina_req = urllib.request.Request(jina_url, headers={'User-Agent': 'Mozilla/5.0'})
            jina_resp = urllib.request.urlopen(jina_req)
            markdown_content = jina_resp.read().decode('utf-8')
            print(markdown_content)
            print()
        except Exception as e:
            print(f"Extraction failed: {e}\n")

if __name__ == "__main__":
    get_weekly_news()
