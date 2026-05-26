---
name: github-auto-merge-workflow
description: Auto-merge PRs on private repos without GitHub Pro using workflow_run trigger instead of branch protection.
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [GitHub, CI/CD, auto-merge, private-repo]
status: stable
---

# GitHub Auto-Merge for Private Repos

## Problem

Branch protection rules (requiring status checks before merge) require GitHub Pro for private repos. The API returns 403: "Upgrade to GitHub Pro or make this repository public to enable this feature."

## Solution

Use `workflow_run` trigger to auto-merge after CI passes — same effect, no Pro needed.

## Implementation

### 1. CI Workflow (e.g., smoke-tests.yml)

```yaml
name: Smoke Tests
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
jobs:
  smoke-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: echo "Tests passed"
```

CI must trigger on BOTH pull_request and push. The `workflow_run` trigger only fires when the referenced workflow runs — if CI only triggers on pull_request, there's no way to test the auto-merge workflow itself or recover from a missed merge.

### 2. Auto-Merge Workflow

```yaml
name: Auto-merge
on:
  workflow_run:
    workflows: ["Smoke Tests"]
    types: [completed]
permissions:
  contents: write
  pull-requests: write
jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: github.event.workflow_run.conclusion == 'success'
    steps:
      - name: Merge PR on green
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          HEAD_BRANCH="${{ github.event.workflow_run.head_branch }}"
          echo "Looking for PRs with head branch: $HEAD_BRANCH"
          PR_NUMBER=$(gh pr list --head "$HEAD_BRANCH" --state open --json number --jq '.[0].number // empty')
          if [ -z "$PR_NUMBER" ]; then
            echo "No open PR found for $HEAD_BRANCH — likely a push-to-main"
            exit 0
          fi
          echo "Auto-merging PR #$PR_NUMBER..."
          gh pr merge "$PR_NUMBER" --squash --delete-branch
          echo "Merged."
```

Use `head_branch` (not `head_sha`) to find the PR. `workflow_run.head_branch` carries the branch name of the triggering run. For PR-triggered smoke tests, this is the PR's head branch (e.g. `update/2026-05-25`). `gh pr list --head "branch-name"` then finds the matching open PR.

## How It Works

1. PR opened → CI workflow runs on the PR branch
2. CI completes (success or failure) → `auto-merge` workflow triggers on main via `workflow_run`
3. Checks `conclusion == 'success'` — does nothing on failure
4. Reads `workflow_run.head_branch` to find the PR by branch name
5. Squash-merges, deletes branch

## Pitfalls

- **Do NOT add a `pull_request` trigger to the auto-merge workflow.** It causes a second run that tries `gh pr merge` outside the `workflow_run` context and fails with "Enable auto-merge for PR | failure". Only use `workflow_run`.
- **The `workflow_run` trigger fires on ALL runs of the CI workflow**, including pushes to main. The `if: conclusion == 'success'` guard handles this — it skips non-PR runs because `gh pr list --head "main"` finds nothing.
- **`workflow_run.head_branch` is set to the triggering run's head branch.** For PR-triggered CI runs, this is the PR branch. For push-to-main CI runs, this is `main`. This is correct behavior — no special handling needed.
- **Use `head_branch`, NOT `head_sha`.** The `head_sha` in `workflow_run` context refers to the merge commit SHA on main, not the PR commit SHA. `gh pr list --head <SHA>` will NOT find the PR. Use `head_branch` for reliable PR lookup.

## Known Failure Modes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Smoke tests pass, auto-merge fails at "Merge PR on green" step | `workflow_run.head_branch` doesn't match the actual PR branch name (e.g. branch was deleted or force-pushed) | Check branch still exists; verify branch name matches exactly |
| Auto-merge silently skips (no PR found) | Push-to-main CI triggered auto-merge, not PR CI | Expected behavior — `gh pr list --head "main"` returns nothing, workflow exits 0 |
| Multiple auto-merge runs for one PR | CI ran twice (PR + push to same branch) | Each CI run triggers one auto-merge run. Second run fails because PR is already merged. Non-critical — log shows "no open PR found" or merge error. |
| Auto-merge hasn't run for days | CI workflow failed, or auto-merge workflow was disabled, or there's a syntax error in the workflow YAML | Check Actions tab for workflow_run trigger status; manually re-run smoke tests from the PR |
| 10+ open PRs backed up, none merged | Auto-merge has been failing silently for days. Check auto-merge run logs for the real error. Most common root cause: `workflow_run` event payload changed (GitHub-side) or the YAML has a subtle bug causing `gh pr merge` to fail. | To recover: manually merge all open PRs that have passing smoke tests |

## Recovery: Manual Batch Merge

When auto-merge has failed and PRs are backed up, manually check and merge:

```bash
# List open PRs
gh pr list --state open --json number,title,headRefName

# For each PR with passing CI checks, merge
# Do NOT merge PRs whose CI status is unknown or failed
gh pr merge PR_NUMBER --squash --delete-branch
```

## Limitations

- Only works for same-repo PRs (not forks)
- No reviewer requirements (needs branch protection / Pro)
- Branch names must match exactly between `workflow_run.head_branch` and `gh pr list --head`
- Public repos can just use branch protection instead (no Pro needed)
- Once auto-merge fails for a PR, it does NOT retry automatically. New PRs also won't merge until the underlying issue is fixed.

## Use Cases

- Nightly commit/PR workflows (skill-versioning, memory exports)
- Bot-driven PRs that should auto-merge on green
- Any private repo workflow needing "merge on green" without Pro

## Support Files

| File | Purpose |
|------|---------|
| `references/agent-skills-recovery-may2026.md` | Specific recovery state for 5L-hermes01/agent-skills (10 stalled PRs as of May 2026) — branch names, merge order, diagnostic steps |
