---
name: skill-versioning
description: Nightly git versioning for skills and private state, with GitHub PR workflow and CI testing.
version: 1.0.0
author: Hermes Agent 01
metadata:
  hermes:
    tags: [skills, versioning, git, github, ci]
status: implemented
---

# Skill Versioning — Implementation

## Overview

Two git repos for tracking Hermes agent evolution:
1. **agent-skills** (public) — shareable skills, compared against upstream
2. **agent-memories** (private) — memory exports, user profile, config

Three-path architecture on disk:
```
/opt/data/repos/agent-skills/           # Git repo — tracks ONLY original work
/opt/data/upstream-hermes-agent/        # Read-only sparse clone (skills/ only)
/opt/data/skills/                       # Consumption directory — rebuilt nightly
```

## Repos

### Skills Repo
- GitHub: `5L-hermes01/agent-skills` (public)
- Local: `/opt/data/repos/agent-skills/`
- Identity: `user.name = "5L-hermes01"`, `user.email = "hermes1@5l-labs.com"`
- Remote: HTTPS with PAT embedded (`https://5L-hermes01:$PAT@github.com/...`)
- **Tracks ONLY original work** — never commits upstream content

### Private Repo
- GitHub: `5L-hermes01/agent-memories` (private)
- Local: `/opt/data/repos/agent-memories/`
- Commits everything (no upstream to compare against)

### Consumption Directory
- `/opt/data/skills/` — where Hermes Agent loads skills from
- Rebuilt nightly by the sync script:
  1. Copy upstream skills/ → `/opt/data/skills/` (baseline)
  2. Overlay agent-skills originals → `/opt/data/skills/` (our files win)
- No `.git` — this is a pure file tree, not a repo

## Nightly Flow

Script: `/opt/data/scripts/nightly-repo-sync.py`
Cron: `nightly-repo-sync` at 03:00 UTC daily

### agent-memories (direct commit)
1. `git add -A`
2. If changes: branch `update/YYYY-MM-DD`, commit, push, open PR
3. Auto-merge via GitHub Actions when smoke tests pass

### agent-skills (upstream-aware)
1. **Update upstream**: `git fetch --depth 1 origin main` into `/opt/data/upstream-hermes-agent/`
2. **Rebuild consumption directory**:
   a. Clear `/opt/data/skills/`
   b. `shutil.copytree` upstream `skills/` → `/opt/data/skills/`
   c. `shutil.copytree` agent-skills repo → `/opt/data/skills/` (overlays our files)
3. **Compare**: Build file map of upstream `skills/`, compare each file in agent-skills repo
4. **Classify**:
   - **New**: exists in repo, not in upstream (our custom skills)
   - **Modified**: exists in both, content differs
5. Stage only new + modified files (skip gitignored, skip `.github/`, `.curator_*`)
6. Branch, commit with `5L-hermes01` identity, push, open PR
7. Auto-merge when smoke tests pass

### Both repos
- Diff report delivered to user in chat for review
- GitHub Actions: smoke-tests.yml + auto-merge.yml

### Upstream clone is sparse (skills/ only)
```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/NousResearch/hermes-agent.git /opt/data/upstream-hermes-agent
cd /opt/data/upstream-hermes-agent
git sparse-checkout set skills/
```
This clones only the `skills/` directory — no docs, tests, plugins, or tools.
Saves bandwidth, disk, and clone time.

## Key Design Decisions

### Separate repo from consumption directory
- **Repo** lives at `/opt/data/repos/agent-skills/` — only original work
- **Consumption** lives at `/opt/data/skills/` — built nightly from upstream + originals
- Keeps git thin: no upstream files in git history, no accidental commits of upstream content
- If the consumption dir gets corrupted, just re-run the nightly build

### Use a separate clone, NOT a remote
```bash
# DON'T: upstream remote in same repo — risk of accidental push
git remote add upstream git@github.com:NousResearch/hermes-agent.git

# DO: read-only clone at separate path
git clone --depth 1 --sparse https://github.com/NousResearch/hermes-agent.git /opt/data/upstream-hermes-agent
git sparse-checkout set skills/
```
Why: keeps upstream completely isolated. No risk of `git push upstream main` by accident.

### Compare by file content, not git tree
- Our repo: `/opt/data/repos/agent-skills/social-media/x-digest/SKILL.md`
- Upstream: `/opt/data/upstream-hermes-agent/skills/social-media/x-digest/SKILL.md`
- Compare by `Path(full).read_bytes()` — handles path differences and content drifts

### Gitignore Handling
- Before staging each file, run `git check-ignore -q <file>`
- Skip if exit code is 0 (ignored)
- Prevents errors on files like `.bundled_manifest`

### Auto-merge Without Branch Protection
- Branch protection requires GitHub Pro for private repos
- Workaround: use `workflow_run` trigger on "Smoke Tests" completion
- Auto-merge workflow fires only when smoke tests conclude with `success`
- Effectively the same as required checks, no Pro needed

## Git Identity

**CRITICAL:** Always use `5L-hermes01` identity in the agent-skills repo.
Do NOT use the upstream bot identity for original work.

```bash
git -C /opt/data/repos/agent-skills config user.name "5L-hermes01"
git -C /opt/data/repos/agent-skills config user.email "hermes1@5l-labs.com"
```

## GitHub Actions Workflows

### smoke-tests.yml
- Runs on PR and push to main
- Checks: leaked secrets (regex), SKILL.md frontmatter (name, description), file encoding, referenced directories

### auto-merge.yml
- Trigger: `workflow_run` on "Smoke Tests" completion
- If success: finds PR by head SHA, runs `gh pr merge --squash --delete-branch`
- If failure: does nothing (PR stays open for manual review)

## Cron Job
- Name: `nightly-repo-sync`
- Schedule: `0 3 * * *` (03:00 UTC)
- Script: `/opt/data/scripts/nightly-repo-sync.py`
- Delivery: results sent to user's chat for review

## Pitfalls
- **Never commit upstream content** into agent-skills — the nightly script explicitly filters for new/modified vs upstream only
- **Consumption dir has no `.git`** — the repo is at `/opt/data/repos/agent-skills/`. Do not initialize git in `/opt/data/skills/`
- **agent-skills uses HTTPS remote** (PAT embedded), agent-memories uses same. Upstream clone must use HTTPS (bot's SSH key doesn't have access to NousResearch repos)
- **`git add -A` can pick up gitignored files** if .gitignore was just created — always `check-ignore` first
- **Only `/opt/data/skills/` is rebuilt**, NOT `/opt/data/scripts/`. Scripts live outside the skills tree and are NOT in any repo. They exist only on local disk and must be backed up separately
- **Missing skill updates**: If PRs back up (10+ open), the auto-merge workflow is likely broken. See `github-auto-merge-workflow` skill's Known Failure Modes section
- **rsync is not installed** — the script uses `shutil.copytree` with `dirs_exist_ok=True` instead. If you install rsync, update the rebuild function to use `rsync -a --delete` for cleaner syncs
- **Upstream sparse clone** only has `skills/` directory checked out. If the nightly script needs files from outside `skills/`, update the sparse-checkout pattern
