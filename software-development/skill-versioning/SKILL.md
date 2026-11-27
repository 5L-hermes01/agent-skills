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

## Landing a change now (not at 03:00)

The nightly rebuild is the only sync, so an edit that must be live this session —
a cron job fires in a few hours — has to be installed by hand and proven. The
consumption copy is disposable; the repo is truth.

1. Edit in the repo (`/opt/data/repos/agent-skills/<category>/<skill>/`).
2. Branch off `main`, commit, push, open a PR to `5L-hermes01/agent-skills`, and
   squash-merge it. Only `origin/main` survives the nightly `reset --hard`; a
   side branch or a working-tree file is deleted along with the skill.
3. Install with a **trailing dot**: `cp -a research/<skill>/. /opt/data/skills/research/<skill>/`.
   `cp -a src dest` when `dest` already exists nests `src` one level deeper, and
   `skills/research/<skill>/<skill>/` then loads as a second skill of the same name.
4. Prove it: `diff -r <repo skill dir> /opt/data/skills/<path>/<skill>` is silent,
   and `grep '^version:'` on the **skills** copy shows the new version.

Replacing a whole skill dir: remove it in one call, copy in the next (or do both
from Python `shutil`). A `rm -rf … && cp -a …` one-liner can stall on approval and
never execute, leaving you reasoning about a state that does not exist.

### Refreshing an upstream PR that went stale

An open PR is a snapshot of its head branch — it does not move when the fork's
`main` moves, so "we have a PR" can mean a PR still carrying a file from weeks
ago. Check the PR itself (`gh pr view <n> --json state,updatedAt,mergeable,files`):
additions that have not changed since the last push mean stale.

To refresh a healthy PR, push new commits onto its head branch instead of opening
a rival PR:

```bash
git ls-remote --heads origin <pr-branch>            # branch must exist on the fork
git worktree add /tmp/wt-pr-<n> -B <pr-branch> origin/<pr-branch>
cp -a <repo>/<skill>/. /tmp/wt-pr-<n>/<skill>/      # trailing dot again
git -C /tmp/wt-pr-<n> commit -am "<msg>"
git -C /tmp/wt-pr-<n> push origin <pr-branch>
git diff --stat origin/<pr-branch> main -- <skill>  # empty = PR head matches your main
```

A worktree keeps the main checkout (and the nightly script's assumptions about it)
untouched. Read the PR back afterwards — state, updatedAt, additions, files —
a push without that read-back is not evidence.

Before pushing into a PR branch, run `git diff --stat upstream/main origin/<pr-branch>`
to see everything the PR actually carries. Unrelated files (registry edits, older
drafts) become yours to defend at review, and unrelated commits from a fork whose
`main` is ahead leak into the diff — branch from `upstream/main` when opening new
work, never from the fork's `main`.

### Your copy shadows upstream forever

The rebuild overlays repo files on top of upstream, so a file you once forked keeps
winning after upstream rewrites it: the local copy freezes at the version you last
saved and silently undoes upstream's changes. Periodically check
`git diff --stat upstream/main main -- <path>`; if history is the only reason the
file differs, adopt upstream's version instead of maintaining two.

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
- **An untracked skill is deleted at the next rebuild**: the rebuild clears `/opt/data/skills/` and overlays only upstream + tracked repo files. A skill that lives only in the repo *working tree* (or on an unmerged `update/local-<date>` branch) disappears from disk the night after the sync commits it, taking its cron entry points with it. After creating or editing a skill, run `git -C /opt/data/repos/agent-skills ls-files | grep <skill-name>`; if it is empty, the skill is living on borrowed time. Fix: merge the `update/local-<date>` PR (or push the files to a feature branch and merge it) so `origin/main` carries them before 03:00 UTC.
- **5L-Labs is a mirror, not a source.** The rebuild's upstream is **NousResearch/hermes-agent**, then this fork's working tree — it never reads 5L-Labs/agent-skills. Merging a skill in 5L-Labs is durability for reviewers, not distribution to this host: if you also delete the fork's copy, the next rebuild removes the skill from `/opt/data/skills/` even though the 5L-Labs PR is merged. Check `grep -nE 'UPSTREAM_REPO|SKILLS_REPO' /opt/data/scripts/nightly-repo-sync.py` before untracking anything, and prove it by rebuilding into a scratch dir (copy `$UPSTREAM_SKILLS`, then overlay the repo) rather than assuming.
- **rsync is not installed** — the script uses `shutil.copytree` with `dirs_exist_ok=True` instead. If you install rsync, update the rebuild function to use `rsync -a --delete` for cleaner syncs
- **Upstream sparse clone** only has `skills/` directory checked out. If the nightly script needs files from outside `skills/`, update the sparse-checkout pattern
