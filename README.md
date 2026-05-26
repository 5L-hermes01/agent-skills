# agent-skills

Original skills and skill extensions authored on top of the [Hermes Agent](https://github.com/NousResearch/hermes-agent) platform.

## Purpose

This repo contains **only original work** — skills created by the agent or substantive modifications to upstream skills that are tracked independently. Upstream skills live in [`NousResearch/hermes-agent/skills/`](https://github.com/NousResearch/hermes-agent/tree/main/skills) and must **not** be copied here.

## Directory Layout

```
research/              # Original research/digest skills
  hn-brief-digest/     # HN Brief digest skill + references
  unified-digest-themes/  # Cross-platform theme taxonomy
social-media/          # Social media skill extensions
  x-digest/            # X/Twitter digest (v3, uses unified themes)
  xurl-cli/            # xurl CLI skill
creative/              # Creative/formatting skills
  structured-digest/   # Generic structured digest formatting
software-development/  # Dev workflow skills
  skill-versioning/    # Skill versioning workflow documentation
github/                # GitHub workflow skills
  github-auto-merge-workflow/
  nightly-upstream-sync/
media/                 # Media skills
  youtube-transcript-download/
autonomous-ai-agents/  # Agent reference docs
  hermes-agent/references/
.github/workflows/     # CI (smoke tests, auto-merge)
```

## Rules for the Agent

1. **Never copy upstream skills here.** If a skill exists in `NousResearch/hermes-agent/skills/`, reference it by path — do not duplicate it.
2. **Only commit original work.** New skills you create, or substantive modifications to upstream skills that need independent tracking.
3. **Use your own author identity.** Commits to this repo should use the agent's own name/email, not the upstream bot identity.
4. **Check `UPSTREAM.md`** before modifying a file to understand its provenance.
