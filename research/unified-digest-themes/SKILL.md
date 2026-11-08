---
name: unified-digest-themes
description: Canonical cross-platform theme taxonomy for all digest pipelines
version: 1.2.0
author: Hermes@5L-Labs.com (NJL)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [themes, taxonomy, digest, classification]
    related_skills: [arxiv]
---

# Unified Digest Theme System

**Canonical taxonomy** for all cross-platform digest jobs: HN Brief, X-Digest, AI-News (weekly/monthly), and arXiv paper summaries.

Load this skill alongside your primary skill (e.g., hn-brief-digest, x-digest) before writing your digest. The theme table below is the single authoritative list — do NOT duplicate it inline in other skills.

## Theme Table

| # | Theme | Description |
|---|-------|-------------|
| 1 | Geopolitics & World Affairs | International conflict, diplomacy, U.S. politics, government power, trade, sanctions — see [reference](references/additional-theme-families.md) |
| 2 | AI & ML Research | Models, architectures, training, benchmarks, agents, papers — see [sub-theme reference](references/ai-ml-research-sub-themes.md) for granular breakdown |
| 3 | Developer Tools & Infrastructure | IDEs, workflows, compute, platforms, agent tooling, MCP |
| 4 | Hardware & IoT | Chips, devices, embedded, robotics, edge inference |
| 5 | Security & Privacy | Vulnerabilities, breaches, encryption, prompt injection, alignment safety |
| 6 | Industry & Business | Funding, companies, products, pricing, policy, regulation |
| 7 | Science & Technology | Physics, bio, space, general science, interdisciplinary research |
| 8 | Career & Leadership | Hiring, recruiting, executive moves, founder/operator stories, identity shifts — see [reference](references/additional-theme-families.md) |
| 9 | Product & Growth | Product strategy, launches, growth loops, retention, monetization, UX — see [reference](references/additional-theme-families.md) |
| 10 | Science & Health | Medical research, biology, brain science, climate, space — see [reference](references/additional-theme-families.md) |
| 11 | Community & Culture | Meta-discussions, events, nostalgia, offbeat, hot takes, memes |
| 12 | Community & Events | Meetups, conferences, webinars, bootcamps, talks, workshops — see [reference](references/additional-theme-families.md) |

## AI & ML Research Sub-Themes

Within the **AI & ML Research** theme, use these sub-themes for granular classification when a section has 3+ items:

| Sub-Theme | Focus |
|-----------|-------|
| Models & Architectures | New model releases, MoE, scaling laws, foundation model specs, capability claims |
| Training & Post-Training | RLHF/DPO/GRPO, fine-tuning, synthetic data, scaling optimization, reward modeling |
| Benchmarks & Evaluation | Leaderboards, evals, capability measurements, test sets, reproducibility |
| Agents & Agent Systems | Agent frameworks, tool use, multi-agent, agent harnesses, coding agents |
| Papers & Theory | Academic preprints, theory, interpretability, alignment, novel methods |

See [references/ai-ml-research-sub-themes.md](references/ai-ml-research-sub-themes.md) for detailed overlap guidance and decision rules.

## Additional Theme Families

See [references/additional-theme-families.md](references/additional-theme-families.md) for detailed sub-themes and overlap guidance for:
- Geopolitics & World Affairs
- Career & Leadership
- Product & Growth
- Science & Health
- Community & Events

## Overlap Resolution

When a story could fit multiple themes:

1. **Identify the primary signal** — what new information does it bring?
   - "New model X released" → AI & ML Research (Models)
   - "Model X is now available on platform Y" → Developer Tools & Infrastructure
   - "Model X costs $Z/token" → Industry & Business
   - "New chip for training models" → Hardware & IoT
   - "New vulnerability in AI systems" → Security & Privacy

2. **If still ambiguous**, ask: *"Where would someone look for this?"*
   - Inference optimization paper → AI & ML Research (Papers) if theoretical; Developer Tools if practical deployment advice
   - Agent safety paper → Security & Privacy if about exploits; AI & ML Research (Agents) if about architectural solutions

3. **Default tiebreaker**: place under the theme that appears earliest in the numbered list above.

## 📚 References

- [Cache-First Digest Aggregation Pattern](references/digest-aggregation-pattern.md) — Cross-platform pattern for building weekly/monthly summary jobs from daily digest caches. Covers the `context_from` limitation, cache contract between harvester and aggregator, scheduling conventions, and the script-based variant.

## Version History

- 1.1.0 (2026-05-24): Added digest-aggregation-pattern.md reference for daily→weekly→monthly cache-first aggregation. Added jargon to related_skills.
- 1.2.0 (2026-06-21): Added additional theme families and sub-themes for geopolitics, career, product, health, and events; linked canonical reference doc.
- 1.0.0 (2026-05-18): Initial canonical taxonomy. 7 top-level themes + 5 AI & ML Research sub-themes.
