# Validation Spec: waytoagi-reader (prep pipeline + delivery)
# Last updated: 2026-09-27
# Change: restored the prep pipeline scripts into the repo (they were untracked
#         in the consumption dir and wiped by the nightly rebuild), moved the
#         handoff JSON off /tmp to /opt/data/cache/waytoagi/, and repointed the
#         delivery cron prompts at the new path.

## Positive Checks (MUST be present)

- [ ] "WaytoAGI Daily prep" (b493f4cf8bf1) cron run reports status ok, not
      "Script exited with code 2" / "WAYTOAGI_DAILY_PREP_FAILED"
- [ ] /opt/data/cache/waytoagi/wt_daily_full.json exists and is valid JSON with
      top-level keys: schema_version, source_url, heading, heading_id, items
- [ ] At least one non-image item carries a non-empty title_en AND content_en
      (content_en is the full translated body, not just a summary)
- [ ] Delivery message contains full article bodies, not a link list
- [ ] Delivery message is plain text, phone-width, no markdown tables/headers

## Negative Checks (MUST NOT be present)

- [ ] No "daily data not ready" / "weekly data not ready" note (means prep failed)
- [ ] No reliance on /tmp/wt_*_full.json as the primary path
- [ ] No stack trace / "No such file or directory: .../waytoagi_pipeline.py"

## Format-Specific Checks

- [ ] Signal: plain text only (no **, #, tables); URLs on their own lines
- [ ] Weekly (7143daa9ad17) reads wt_week_full.json from the same durable dir;
      it fires 15:00 prep -> 16:00 delivery UTC on Sundays, so the prep must
      finish inside that 60-minute window

## Durable-path invariant

- [ ] Both files survive a nightly rebuild (03:00 UTC) and a container restart:
      they live in /opt/data/cache/waytoagi/, outside /tmp and outside the
      consumption skills dir