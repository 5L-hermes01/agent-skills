#!/usr/bin/env python3
import urllib.request
import xml.etree.ElementTree as ET
import sys
from datetime import datetime, timedelta, timezone

def get_news(days_back):
    url = "https://news.smol.ai/rss.xml"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        response = urllib.request.urlopen(req)
        xml_data = response.read()
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"Error fetching feed: {e}")
        return

    # Use calendar-day cutoff: start of today minus days_back (UTC midnight)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_date = today_start - timedelta(days=days_back)
    
    print(f"=== AI News Summaries for the last {days_back} days ===")
    count = 0
    for item in root.findall('.//item'):
        pub_date_str = item.findtext('pubDate') # e.g. Wed, 08 Apr 2026 05:44:39 GMT
        try:
            pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
            
        if pub_date >= cutoff_date:
            title = item.findtext('title')
            link = item.findtext('link')
            desc = item.findtext('description')
            print(f"\n[{pub_date.strftime('%Y-%m-%d')}] {title}")
            print(f"URL: {link}")
            print(f"Summary: {desc}")
            count += 1
            
    if count == 0:
        print("No news found in that timeframe.")

if __name__ == "__main__":
    days = 1
    if len(sys.argv) > 1:
        days = int(sys.argv[1])
    get_news(days)
