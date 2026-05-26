# Agent-Skills Auto-Merge Recovery (May 2026)

## Situation
As of 2026-05-25, the `5L-hermes01/agent-skills` repo had **10 open, unmerged PRs** (#29-#38) dating back to May 21. All had passing smoke tests. The auto-merge workflow ran after each successful smoke test but failed at the "Merge PR on green" step.

## Known Open PRs

| PR | Title | Created | Branch |
|----|-------|---------|--------|
| #29 | Nightly update 2026-05-21 | May 21 | update/2026-05-21 |
| #30 | Local customizations 2026-05-22 | May 22 | update/local-2026-05-22 |
| #31 | Nightly update 2026-05-22 | May 22 | update/2026-05-22 |
| #32 | Nightly update 2026-05-23 | May 23 | update/2026-05-23 |
| #33 | Local customizations 2026-05-23 | May 23 | update/local-2026-05-23 |
| #34 | Upstream sync 2026-05-24 | May 24 | update/upstream-2026-05-24 |
| #35 | Local customizations 2026-05-24 | May 24 | update/local-2026-05-24 |
| #36 | Nightly update 2026-05-24 | May 24 | update/2026-05-24 |
| #37 | feat(arxiv): add daily digest workflow | May 24 | feat/arxiv-digest-workflow |
| #38 | Nightly update 2026-05-25 | May 25 | update/2026-05-25 |

## Diagnosing the Failure

All auto-merge runs showed `conclusion: failure` at the "Merge PR on green" step. To check:

```bash
# List recent auto-merge workflow runs
gh run list --workflow auto-merge.yml --limit 5 --json number,conclusion,headBranch

# Check specific run logs
gh run view RUN_ID --log-failed
```

Common failure modes at this step:
1. `gh pr merge` exits non-zero — could be merge conflict, GITHUB_TOKEN permissions, or squash commit message issue
2. Branch name mismatch — if the smoke test ran on a different SHA than the PR's current head
3. `GITHUB_TOKEN` lacks `pull-requests: write` permission on the auto-merge workflow

## Recovery Steps

1. For each PR with passing smoke tests, check if it can be cleanly merged:
   ```bash
   gh pr checks PR_NUMBER
   gh pr view PR_NUMBER --json mergeable,mergeableState
   ```

2. Manually merge passing PRs (oldest first to minimize conflicts):
   ```bash
   gh pr merge PR_NUMBER --squash --delete-branch
   ```

3. After all PRs cleared, un-pause the nightly sync cron job:
   ```bash
   cronjob action='update' job_id='11db721edf4f' schedule='0 3 * * *' resume=true
   ```

## Related

- `nightly-upstream-sync` skill — main pipeline that creates these PRs
- `github-auto-merge-workflow` skill — the auto-merge runner
- The nightly sync runs at 03:00 UTC via cron job `11db721edf4f` (currently paused)