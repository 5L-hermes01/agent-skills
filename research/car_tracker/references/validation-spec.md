# Validation Spec: car_tracker
# Last updated: 2026-07-27
# Change: Phone-width bulletin — top 2 genuinely new arrivals, target-options columns, URLs after table

## Positive Checks (MUST be present)

- [ ] Title is "# Daily Car Market Bulletin (New Listings)" — NOT "New Listings & Cheapest Deals"
- [ ] Subtitle mentions Yonkers, NY coordinates
- [ ] Each trim header shows target OTD price when available (e.g. "— target $58,451")
- [ ] Each trim header shows NO target price when target_otd_price is null (e.g. Pacifica, Lexus TX)
- [ ] Table has exactly 6 columns: #, Dealer (mi), Price, Δ, Color, C/O
- [ ] Column `#` contains row numbers (1, 2) matching the URL index list below
- [ ] Δ values are formatted as "$X,XXX" (no "+" prefix, no leading space)
- [ ] Price values are formatted as "$XX,XXX" (no leading space between $ and digits)
- [ ] Dealer column contains state code and distance in "XX NNNmi" format (no parentheses, no em-dash)
- [ ] C/O column uses compact format like "3/3,2/2" (NOT "C: 3/3 | O: 2/2")
- [ ] Color column uses abbreviated names (Pearl, Storm, Black, Blue, etc.) — NOT full names
- [ ] Dealer URLs appear as numbered list AFTER the table (1. https://...)
- [ ] Benchmark line appears after URLs: "*Benchmark: cheapest active $XX,XXX — Dealer ST NNNmi*"
- [ ] At most 2 rows per trim in the New Arrivals section
- [ ] "No new listings appeared on the market since last check." when state is current
- [ ] "No active new inventory matching specifications found." when API returns zero matches

## Negative Checks (MUST NOT be present)

- [ ] No "🏆 Top 5 Cheapest Active Deals" section
- [ ] No "New Listings & Cheapest Deals" in title
- [ ] No inline markdown links inside table cells (no "[Dealer Site](...)" or "[Visor](...)" in table)
- [ ] No "Visor Link" or "Dealer Site" column headers
- [ ] No "Loc / Dist" or "Price (% off MSRP)" column headers (old format)
- [ ] No full 17-char VINs in table rows (only last 8 chars)
- [ ] No "C: " or "O: " prefixes in C/O column
- [ ] No leading space between "$" and number in Price or Δ columns

## Format-Specific Checks

- [ ] Table separator line matches column count: exactly 6 pipe-separated dash groups
- [ ] No raw HTML or unescaped markup
- [ ] Trims appear in order: Limited, Nightshade, Pacifica, TX 350
