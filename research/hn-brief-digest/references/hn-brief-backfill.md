# HN Brief Cache Operating Procedure

Use this document when missing dates are detected under `/opt/data/cache/hn-brief/`.

## Backfill script

Script: `/opt/data/scripts/hn-brief-backfill.py`

### When to use

- Daily/weekly/monthly digest jobs report no cache for a date.
- You know the date is missing because `/opt/data/cache/hn-brief/YYYY/MM/DD/formatted-digest.txt` does not exist.
- You want to backfill a date range for weekly or monthly aggregation.

### When NOT to backfill

- The date exists but is >30 days old (re-fetch is acceptable, but not required).
- The date is available via cron-output salvage under `/opt/data/cron/output/`.
- The site or source is unavailable for legal/policy reasons.

### Usage

```bash
# Single date
python3 /opt/data/scripts/hn-brief-backfill.py --date YYYY-MM-DD

# Oldest date first
python3 /opt/data/scripts/hn-brief-backfill.py --count 3

# Newest date first
python3 /opt/data/scripts/hn-brief-backfill.py --count 5 --newest-first --range-start 2026-04-27 --range-end 2026-05-31
```

## Cache write rules

All cache writes MUST use terminal-based atomic writes.

Do not write to cache via `write_file` inside cron sessions.

