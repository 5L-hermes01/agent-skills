# HN Brief Content Extraction: Cloudflare + SPA

## Problem
`web_extract`, `curl`, wget, and direct `fetch('summaries/YYYY/MM/DD.md')` from a fresh browser context all receive 403 from Cloudflare. The SPA itself succeeds because Cloudflare's challenge completes during page load.

## Verified Approach
1. Launch headless Playwright Chromium.
2. Navigate to `https://hn-brief.com` with `waitUntil: 'networkidle'`.
3. Wait at least 8-10 seconds so the challenge completes and cookies are set.
4. Execute page-side JS to call `fetch()` for `summaries/YYYY/MM/DD.md` and `summaries/YYYY/MM/DD-digest.md`.
5. Persist both responses to disk.

The SPA's source also references `summaries/archive.json`; that endpoint may help discover available dates programmatically.

## Fallback Order
1. Browser toolset with article view + DOM extraction.
2. Playwright script running JS `fetch()` inside loaded page context.
3. Local cron-output files already captured for the same date.