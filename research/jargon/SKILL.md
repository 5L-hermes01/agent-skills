---
name: jargon
description: Detect, decode, and track domain-specific jargon across digest pipelines
version: 1.2.1
author: Hermes@5L-Labs.com (NJL)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [jargon, terminology, plainspeak, digest, acronyms]
    related_skills: [arxiv]
---

# Jargon Detection & Decoding

Detects and translates domain-specific jargon (acronyms, technical terms, out-of-distribution words) in digest content. Each term is classified by theme (from unified-digest-themes taxonomy) and sophistication level, with plainspeak translations at multiple reading levels.

## The Jargon Registry

The master dictionary lives at [references/jargon-registry.json](references/jargon-registry.json). Each entry has:

| Field | Description |
|-------|-------------|
| `term` | The jargon word/acronym (key in JSON, e.g. "DPO") |
| `theme` | Theme from unified-digest-themes taxonomy |
| `sub_theme` | Optional sub-theme for AI & ML Research items |
| `source_level` | Highest sophistication level where it originates |
| `plainspeak.doctor` | Domain-expert explanation (full technical precision) |
| `plainspeak.high-school` | Tech-literate generalist explanation |
| `plainspeak.kindergarten` | General audience explanation (short, intuitive) |
| `first_seen` | ISO date first encountered |
| `last_seen` | ISO date most recently seen |
| `seen_in` | Array of source identifiers (e.g. "arxiv:cs.CL", "x:list-ai-high-signal") |

### Sophistication Levels

| Level | Audience | Example ("DPO") |
|-------|----------|-----------------|
| doctor | Domain experts | "Direct preference optimization using pairwise preferences to align language models with human values" |
| high-school | Tech-literate generalists | "Training AI by showing it which outputs are better and letting it learn from comparisons" |
| kindergarten | General audience | "Teaching AI right from wrong by example" |

## Workflow

### Step 1: Load registry

Read `references/jargon-registry.json` via skill_view(name='jargon', file_path='references/jargon-registry.json') to get known terms. The registry persists across sessions — always load the latest.

### Step 2: Scan content for known jargon

For each digest item (paper title/abstract, tweet, story headline):
- Check if any registered term appears (case-insensitive match)
- Bump `last_seen` and append the source id (e.g. `arxiv:cs.CL`, `ai-news:2026-11-03`) to `seen_in` for every hit — saturated or not. This is the tracking contract that feeds the weekly prevalence report and the jargon-notify job.
- For non-saturated terms found, the term is a DISPLAY CANDIDATE — whether it is displayed depends on the output channel (see Ownership below).
- Within a single digest, track which terms have already been explained and skip repeats. If LLM was explained in paper 1, don't re-explain it in paper 7.

### Step 3: Detect unknown jargon

For unfamiliar capitalized acronyms (3-8 chars written in ALL CAPS) or domain-specific terms not in the registry:
- Infer theme from context using unified-digest-themes taxonomy
- Generate a plainspeak definition at all three levels using available local model or reasoning
- Append it as a NEW registry entry (all required fields) — this is mandatory; without it the jargon-notify job never sees the term.

### Step 4: Update registry

For newly confirmed terms (verify with the user or infer from context):
- Read the registry file via skill_view
- Add a new entry with all required fields
- Write via skill_manage write_file to update the reference

## Ownership (WHO PRESENTS JARGON)

- **Daily digest jobs (arxiv-daily-papers, daily-ai-news, and weekly/monthly digests): do NOT include a Jargon section in delivered output.** They scan, detect, and update the registry only. The digest's job is content; jargon is tracked, not shown.
- **jargon-notify (dedicated daily job, deterministic no_agent script): the only owner of jargon presentation.** It diffs registry vs posted-state, scans the last-24h feed corpora for frequency, and posts new-term announcements (with complexity-graded meanings + frequency) to its Discord channel.
- **Ad-hoc paper-pile digests (interactive): may include a jargon line inline since the user reads them on Signal and explicitly asked for decoding.** Keep it short, kindergarten-level, one block.
- **Saturated terms never appear in any output.** They are tracking-only.

## Output in Digests

### For ad-hoc / interactive digests (the only ones that display jargon)

When jargon is detected in a digest item, append the plainspeak note with an education level label. Saturated terms (those the audience already knows) are suppressed — they never appear in output even if detected in the text. Within a single digest, each term is explained at most once (on first encounter).

For known non-saturated terms:

```
**Jargon:** 🎒 [kindergarten] DPO = teaching AI right from wrong by example. LLM = a smart computer brain that understands words.
```

For newly detected terms found during this run:

```
**Jargon:** 🆕 New term: BPE = a common way to split words into smaller pieces. LM = a computer model that understands language.
```

Group multiple jargon notes on the same `**Jargon:**` line if many terms appear in one paper. Separate entries with periods. Use kindergarten level for general-audience channels, high-school for technical channels.

### For cron digest jobs (arxiv, ai-news, weekly/monthly)

No jargon output. The deliverable is content grouped by theme plus links; a Jargon section is never emitted. Any job that was emitting one must stop; the jargon-notify job announces new terms.

## Registry Maintenance

- New terms are discovered during digest runs (Step 3)
- The registry grows organically — there is no "complete" list
- Terms marked `"saturated": true` are never displayed to the audience (suppressed from all digest output), but they remain in the registry for tracking. Mark common baseline terms as saturated when they appear so often that re-explaining them adds noise.
- Periodically consolidate: if a term hasn't been seen in 90 days, flag for possible removal
- First seen/last seen dates enable usage tracking over time

## Version History

- 1.2.0 (2026-06-14): Added saturation filter — terms marked `"saturated": true` are suppressed from digest output. Added per-digest deduplication to avoid re-explaining the same term across multiple papers in one run.