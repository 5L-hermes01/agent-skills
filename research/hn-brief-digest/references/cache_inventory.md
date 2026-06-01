# HN Brief Cache Inventory / Known Gap

Observed `formatted-digest.txt` files as of 2026-06-01:

- `/opt/data/cache/hn-brief/2026/05/23/`
- `/opt/data/cache/hn-brief/2026/05/26/`
- `/opt/data/cache/hn-brief/2026/05/27/`
- `/opt/data/cache/hn-brief/2026/05/28/`

Impact:
- Popularity tracker probes dates such as `2026-05-02`, `2026-05-25`, `2026-04-27` and bails because no cache exists.
- Weekly/monthly digests are also exposed to missing-source days when they walk the cache tree.

Use this file as a backfill checklist against which dates still need their daily scrape+save.
