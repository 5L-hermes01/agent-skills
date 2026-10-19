---
name: packers-prop-betting
description: Packers game day? Build verified prop and game-market picks.
version: 1.0.0
author: Hermes Agent 01
license: MIT
metadata:
  hermes:
    tags: [nfl, betting, props, packers, analysis]
---

# Packers Weekly Player-Prop Parlays

## When to Use
- The user asks for Packers/Cowboys-or-opponent player-prop analysis, parlays, or betting picks on a game day.
- The `packers-prop-scan` cron fires and tonight may be a GB game (reply [SILENT] if not).
- Regular season 2026 ends ~Jan 11; pause usage/cron after elimination or season end.

Produces two deliverables per game day: (0) GAME MARKETS — spread + total analysis, rankings, spread×total parlay; then player props — three parlays (Safe / Balanced / Upside) + top-5 ranked props. Both from verified data only. Run ~4+ hours before kickoff. Regular season 2026 ends ~Jan 11.

## Hard rules (never violate)
- NEVER invent odds, injury statuses, lines, or stats. Every price carries a source; from a published article not a live feed -> label "reported, verify in-app."
- No live sportsbook API from this box. Line sources: DraftKings Network, The Lines (thelines.com), RotoGrinders, SportsGambler, Covers, beat papers (Clarion-Ledger/USA Today network, jsonline). web_search with the game date, not memory.
- Always close with sizing guidance (edges are single-digit pts/leg; parlays multiply variance+vig, not edge; correlated legs share one brain; cap total exposure).
- Signal output: plain text, no wide tables, bullets and labeled lines.

## Game identification
ESPN scoreboard JSON: `https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=YYYYMMDD` -> kickoff, venue, weather block, game status (verify pre!), odds provider. Confirm tonight's GB opponent before building; if no GB game that date -> reply [SILENT].

## Procedure
1. Game facts (parallel web_extract): ESPN scoreboard + PFR `teams/gnb/{year}.htm` + opponent `teams/{opp}/{year}.htm`. Saved pages truncate head+tail — the stats tables are in the HIDDEN MIDDLE; read_file the saved cache file middle: record, rank rows, injury table, passing/rush-receiving tables, TD log.
2. Injuries: PFR Week-N tables + web_search "{team} injury report Friday out questionable" + Saturday travel/downgrade news. IR/ACL absences noted explicitly.
3. Lines: web_search "{opp} vs Packers player props {month day year}". Extract per prop: player, market, line, price, book. Cross-check two sources where a price anchors a pick.
4. Weather: ESPN block + Open-Meteo GB (44.512,-88.065) hourly at kickoff. Wind>15mph or precip>30% changes passing legs — say so.
5. Analysis:
   - Team level: pass D yards + NY/A + TD ranks, rush D, RZ%, median-vs-mean passing yards per QB.
   - Per leg: estimated hit prob with stated drivers (avg, median, matchup rank, injury-adjusted coverage, target share) vs implied from price. Skip <3pt-edge props and SAY why (ATD +115 vs ~48% model = trap; passing-yard lines at the player's own average are fair-priced).
   - Parlay A: 2 legs you'd single-bet. B: 3 legs, independent-ish best edges. C: up to 5 legs, one thesis — disclose cluster risk, discount own joint estimate.
6. Compute: combined decimal from American odds, break-even=1/decimal, $10 return incl stake, honest hit range, name BEST overall with reason.
7. Correlation section MANDATORY: the single script all legs ride, what kills 2-3 legs together, any hedge leg.
8. Top-5 props by estimated edge + explicit skips with prices.

## Known traps
- PFR truncation hides the stats (middle). ESPN scoreboard shows finals if date is wrong. Lines move on late practice news ("full practice" flips risky props) — note last-verified. GB run rank dead last -> pass-first script for their QB every week; check opponent NY/A rank, not yards rank alone.

## Game markets (spread & total) — run BEFORE props

Extra sources: VegasInsider matchup page (open/consensus per-book grid), ActionNetwork game page (opens), Probetrics (9-book current grid + movement trail), FanDuel Research (FD history), espn.com/nfl/odds/_/gameId/<id>, Dimers prediction page (model win% + best available prices), TheSpread article (ticket splits). Extract per side: current spread/ML/total by book, opens, movement history, public ticket %. If sources disagree on movement history (e.g. first-seen DAL -1.5 vs older open GB -3), SAY SO — current consensus is what matters.

Method:
- Fair total: each team = (own PF/g + opp PA/g)/2, summed. THEN check whether market drift encodes info the averages lag: injury-depleted secondaries, RZ TD% ranks both directions, turnover-forced rank vs opposing QB INT rate, zero-run games both sides => pass volume + late-clock scripts. Only claim a total edge when an OUTLIER book's inflated number is fadeable; never fade consensus with stale averages.
- Spread: SRS with SOS differential (raw SRS gap misleads when schedules differ), x-W-L, rest/travel deltas (Thursday game = extra rest), venue. Coin-flip lines are usually efficient — default spread answer is NO BET; value lives in price (dog at +113 vs +105, alternate -1 push insurance), not side.
- Per recommendation report: line + price + book, projected score, est cover %, break-even from price, key reasons, kill factors, confidence 1-10.
- Rank: best ATS, best total, best 2-leg spread×total. Correlation section MANDATORY: dog+over / fav+under are frequently the SAME script (positive correlation — joint prob exceeds naive product, but one bad script kills both); state joint estimate, break-even, EV. $10 returns incl stake. Name THE single strongest wager; "no bet tonight" is a valid, shippable conclusion when nothing clears vig.
- Movement drivers are labeled inference unless a source reports them.

## Cron
Job `packers-prop-scan` delivers both deliverables to Nick's Signal only on GB game days; [SILENT] otherwise. Pause after season ends.
