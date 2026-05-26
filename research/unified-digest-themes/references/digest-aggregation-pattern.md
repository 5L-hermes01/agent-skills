# Cache-First Digest Aggregation Pattern

Cross-platform design pattern for multi-timescale digest pipelines (daily → weekly → monthly).

## Problem

You want weekly and monthly summaries of a daily digest source (HN Brief, X/Twitter, arXiv, RSS feeds). A naive approach uses `context_from` on the cronjob tool to inject recent daily outputs — but `context_from` only returns the **most recent completed output** of each referenced job, not all N runs across the period. It cannot aggregate 7 or 30 daily outputs.

## Solution: Cache-First Aggregation

Each daily digest job writes its formatted output to a **filesystem cache** as a deterministic side effect. Weekly/monthly aggregator jobs read from the same cache instead of depending on `context_from`.

```
Daily job (harvester) ──➤ writes to ──➤ /opt/data/cache/<source>/YYYY/MM/DD/formatted-digest.txt
                                        │
Weekly job (aggregator) ──reads 7 files──┘
Monthly job (aggregator) ─reads ~30 files─┘
```

### Roles

| Role | Responsibility | Example |
|------|----------------|---------|
| Harvester | Fetches source data, formats it, writes cache file. Runs daily. | hn-brief-digest (22:00 UTC) |
| Aggregator | Reads N cached harvester files, synthesizes a higher-level summary. Runs weekly or monthly. | hn-brief-weekly-digest (Sun 23:00 UTC), hn-brief-monthly-digest (1st 20:00 UTC) |

### Cache Contract

The harvester commits to:

1. **Save after formatting**: Write `formatted-digest.txt` to `/opt/data/cache/<source>/YYYY/MM/DD/` as the **last step** before delivery. Use `write_file()` for atomic writes.
2. **Use yesterday's date**: Summaries cover the previous day's news, so the cache path uses `today - 1 day`.
3. **Check before fetching**: If the cache file already exists and is < 30 days old, skip the fetch entirely and deliver from cache.
4. **30-day validity**: After 30 days, re-fetch is allowed (aggregator jobs that read old files should handle missing days gracefully).

The aggregator commits to:

1. **Scan the cache directory** for the last N days of files. Use `find` or glob to discover available dates — some days may be missing (weekends, holidays, failures).
2. **Handle gaps gracefully**: If only 5 of 7 daily files exist, summarize from what's available. Note the gap.
3. **Cache its own output** at `/opt/data/cache/<source>/weekly/` or `monthly/` with ISO-date naming.
4. **Do NOT fetch source data directly** — the aggregator's value is synthesis, not re-harvesting.

## Implementation Details

### Harvester Cache Path Convention

```
/opt/data/cache/<source>/YYYY/MM/DD/formatted-digest.txt
```

Where `<source>` is:
- `hn-brief` — HN Brief daily digests
- `x-digest` — X/Twitter high-signal digests (not yet implemented)
- `arxiv` — arXiv paper summaries (not yet implemented)

### Aggregator Output Path Convention

```
/opt/data/cache/<source>/weekly/YYYY-Www-formatted-digest.txt    (ISO 8601 week)
/opt/data/cache/<source>/monthly/YYYY-MM-formatted-digest.txt
```

### Cron Job Scheduling

| Job | Schedule | Notes |
|-----|----------|-------|
| Daily harvester | `0 22 * * *` | Runs 22:00 UTC every day |
| Weekly aggregator | `0 23 * * 0` | Sunday 23:00 UTC — 1h after daily so today's cache is ready |
| Monthly aggregator | `0 20 1 * *` | 1st of month 20:00 UTC — reads last ~30 daily caches |

The 1-hour gap between daily harvester and weekly aggregator on Sunday ensures the harvester has written today's cache before the aggregator reads it.

## When NOT to Use This Pattern

- **Single-run jobs that don't feed downstream consumers** — no cache needed.
- **Real-time or intraday summaries** — use a different data bus (database, API).
- **context_from is sufficient** — when you need only the most recent output of one or two upstream jobs, `context_from` is simpler.

## Variant: Script-based Aggregation

For sources that already have a script-based fetcher (e.g., `smol_news_weekly.py` for AI-News RSS), the aggregator can call the script directly with a different time window instead of reading cached files:

- Weekly: `python3 scripts/smol_news_weekly.py`
- Monthly: `python3 scripts/smol_news_monthly.py` or `python3 scripts/smol_news_aggregator.py 30`

This avoids the cache layer entirely when the source is a script, not a browser-harvested SPA.

## Version History

- 1.0.0 (2026-05-24): Initial pattern documentation. Derived from HN Brief daily → weekly → monthly pipeline design.