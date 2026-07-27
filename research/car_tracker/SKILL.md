---
name: car_tracker
description: Publishes a daily bulletin of new arrivals for monitored vehicle trims, with target-options compliance checks and market benchmark pricing.
version: 1.2.0
author: Antigravity Agent
license: MIT
metadata:
  hermes:
    tags: [monitoring, tracking, daily-bulletin, visor-api, auto-pricing]
---

# Daily Car Tracker Skill

This skill tracks and publishes a daily bulletin of genuinely new vehicle listings for your monitored trims. It compares fresh Visor API listings against a local state database (`data/seen_listings.json`) to surface only previously unseen inventory. Each new arrival is checked for target options compliance and benchmarked against the cheapest active market listing.

## Setup & Credentials

Configure the following environment variables or add them to your `.env` file:
*   `VISOR.VIN_API_KEY` (or `VISOR_API_KEY`): Required. Bearer token to fetch live listings.

## Target Config

The tracker monitors target profiles specified in `config/target_profiles.json`. If this file is missing, it falls back to built-in defaults:
1.  Toyota Grand Highlander (Hybrid Limited AWD) — target $58,451
2.  Toyota Grand Highlander (Hybrid Nightshade AWD) — target $56,110
3.  Chrysler Pacifica (Pinnacle AWD) — target TBD
4.  Lexus TX (350 AWD) — target TBD

### Custom JSON Config Example (`config/target_profiles.json`)
```json
{
  "grand_highlander_hybrid_limited_awd": {
    "key": "grand_highlander_hybrid_limited_awd",
    "year": 2026,
    "make": "Toyota",
    "model": "Grand Highlander",
    "trim": "Hybrid Limited AWD",
    "target_otd_price": 58450.85,
    "sample_vin": "5TDACAB53TS25G407",
    "required_trim_keywords": ["LIMITED"],
    "requires_awd": true,
    "requires_hybrid": true
  }
}
```

## How to Run

Execute the tool via the project's virtualenv Python interpreter:

```bash
python research/car_tracker/scripts/publish_deals.py
```

## Output Format

Running `publish_deals.py` generates a structured Markdown bulletin designed for phone-width display:

*   **Header**: Each trim shows its target OTD price (e.g. `— target $58,451`)
*   **🆕 New Arrivals (Top 2 Closest)**: The 2 closest genuinely-new listings (by proximity to Yonkers, NY), sorted by distance
*   **Phone-width columns**: `#` | `Dealer (mi)` | `Price` | `Δ` | `Color` | `C/O`
    *   `#`: Row index matching the numbered URL list below the table
    *   `Δ`: Price delta from the cheapest active listing on the market
    *   `Color`: Abbreviated paint color (e.g. Pearl, Storm, Black)
    *   `C/O`: Compact target-options compliance (e.g. `3/3,2/2` = 3 of 3 critical, 2 of 2 optional)
*   **Dealer URLs**: Numbered reference list after the table, indexed by row number. Each table row's `#` column maps to the corresponding URL in the list.
*   **Benchmark line**: Shows the cheapest active listing price and location for comparison
*   **State caching**: Vehicle colors, MSRPs, and feature summaries are cached in `seen_listings_db` for zero-latency repeat runs