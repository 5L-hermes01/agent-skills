---
name: jargon
description: Detect, decode, and track jargon terms across digest pipelines. Maintains a registry of domain-specific acronyms and terms with plainspeak translations at multiple sophistication levels.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [jargon, terminology, plainspeak, digest, acronyms]
    related_skills: [unified-digest-themes, x-digest, arxiv]
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
- If found, note the term and include its definition LABELED with the education level: `🎒 [kindergarten] TERM = definition`
- Use kindergarten level for general-audience channels, high-school for technical channels, doctor for expert-only channels

### Step 3: Detect unknown jargon

For unfamiliar capitalized acronyms (3-8 chars written in ALL CAPS) or domain-specific terms not in the registry:
- Infer theme from context using unified-digest-themes taxonomy
- Generate a plainspeak definition at all three levels using available local model or reasoning
- Append a note with level label: `🆕 New term: TERM = [kindergarten-level definition]`

### Step 4: Update registry

For newly confirmed terms (verify with the user or infer from context):
- Read the registry file via skill_view
- Add a new entry with all required fields
- Write via skill_manage write_file to update the reference

## Output in Digests

When jargon is detected in a digest item, append the plainspeak note with an education level label. For known terms:

```
**Jargon:** 🎒 [kindergarten] DPO = teaching AI right from wrong by example. LLM = a smart computer brain that understands words.
```

For newly detected terms found during this run:

```
**Jargon:** 🆕 New term: BPE = a common way to split words into smaller pieces. LM = a computer model that understands language.
```

Group multiple jargon notes on the same `**Jargon:**` line if many terms appear in one paper. Separate entries with periods. Use kindergarten level for general-audience channels, high-school for technical channels.

## Registry Maintenance

- New terms are discovered during digest runs (Step 3)
- The registry grows organically — there is no "complete" list
- Periodically consolidate: if a term hasn't been seen in 90 days, flag for possible removal
- First seen/last seen dates enable usage tracking over time

## Version History

- 1.1.0 (2026-05-24): Step 2/3 output now includes education level labels (🎒 [kindergarten], 🆕 New term). Output format shows `**Jargon:**` line with labeled definitions for Discord markdown digests.
- 1.0.0 (2026-05-24): Initial skill. JSON registry with plainspeak at doctor/high-school/kindergarten levels. Detection workflow for digest pipelines.