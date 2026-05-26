# Upstream Provenance

This file documents which skills in this repo have a relationship to the upstream [`NousResearch/hermes-agent/skills/`](https://github.com/NousResearch/hermes-agent/tree/main/skills) directory.

## Derived from upstream (substantively modified)

| File | Upstream path | What changed |
|------|--------------|--------------|
| `social-media/x-digest/SKILL.md` | `social-media/x-digest/SKILL.md` (removed upstream) | v2→v3: replaced inline theme list with reference to `unified-digest-themes` skill, added primary-signal rule for theme assignment |

## Original (no upstream equivalent)

Everything else in this repo was created here and has never existed in the upstream repository:

- `research/hn-brief-digest/` — HN Brief digest skill
- `research/unified-digest-themes/` — cross-platform theme taxonomy
- `creative/structured-digest/` — generic structured digest formatting
- `software-development/skill-versioning/` — skill versioning workflow
- `github/github-auto-merge-workflow/` — GitHub auto-merge workflow skill
- `github/nightly-upstream-sync/` — nightly upstream sync skill
- `social-media/xurl-cli/` — xurl CLI skill
- `media/youtube-transcript-download/` — YouTube transcript download skill
- `autonomous-ai-agents/hermes-agent/references/pre-upgrade-backup.md` — pre-upgrade backup methodology

## Merge rule

> If a skill exists in `NousResearch/hermes-agent/skills/`, do **not** commit a copy here. Reference it by path instead. Only commit here if you have created a new skill or made substantive modifications worth tracking independently.
