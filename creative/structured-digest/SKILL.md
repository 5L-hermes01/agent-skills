---
name: structured-digest
description: Format long-form text (transcripts, articles, meeting notes, research papers) into structured bullet-point digests grouped by theme. Use when the user wants a concise, scannable summary of dense content.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [formatting, digest, summary, structured-output]
---

# Structured Digest Formatting

Transform dense text into structured, scannable bullet-point digests grouped by theme. Works with any long-form content — transcripts, articles, meeting notes, research papers, thread dumps.

## Format Specification

```
[Title] (what matters):
    •    Core concept = definition.
    Short explanation.
    •    Second concept:
    ◦    Detail or example.
    ◦    Another detail.
    •    Key distinction between X and Y:
    ◦    X = this
    ◦    Y = that
    •    Practical relevance:
    ◦    Use case 1.
    ◦    Use case 2.
    •    Big insight: main takeaway in one line.

    •    Caveats or open questions:
    ◦    Limitation or note.
        [Optional: next-action offer]
```

## Style Rules

- Open with a short title and context line (speaker, source, length/date)
- Group by **theme**, not by chronology or engagement — identify the central topics
- Use thematic sections with a **bold label** and a short intro sentence
- `•` for main points, `◦` sub-bullets for details/examples
- **Bold** key terms on first mention
- No markdown headers, no emoji dividers
- Concise — each bullet should be one or two lines max
- End with a "next step" or question if natural

## Theme Selection

When grouping content, identify themes organically from the material. Common patterns:

- **Technical content**: Models & Architectures, Tools & Workflows, Infrastructure, Research, Benchmarks
- **Business content**: Strategy, Metrics, Risks, Decisions, Action Items
- **News/discussion**: Key Developments, Community Reaction, Analysis, Open Questions
- **Meeting notes**: Decisions Made, Action Items, Blockers, Follow-ups

If a point could fit multiple themes, use the **primary signal** rule: place it under the most specific matching theme based on its central new information.

## Workflow

1. **Read** the full source content
2. **Identify themes** — scan for recurring topics, don't force a predefined list
3. **Extract key points** — one bullet per distinct idea, with sub-bullets for supporting details
4. **Filter** — drop filler, pleasantries, repetition. Keep only meaningful content
5. **Order** — lead with the most important/novel themes, end with caveats or open questions
6. **Verify** — re-read to ensure no key insight was dropped and no theme is redundant

## Fallback for Raw/Timestamped Text

When processing raw text (e.g. timestamped transcripts):

1. Strip timestamps (remove patterns like `0:05 `, `12:34 `, or `1:05:23 `)
2. Join remaining text and split into sentences
3. Filter to keep only meaningful sentences (length > 20 characters)
4. Group sentences into thematic sections
5. Format as structured bullets per the style rules above
6. Bold key terms on first mention
