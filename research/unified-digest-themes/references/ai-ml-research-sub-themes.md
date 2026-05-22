# AI & ML Research — Sub-themes Reference

This document defines the sub-themes within **AI & ML Research** for the unified cross-platform digest system. These provide consistent granularity across HN Brief, X-Digest, news aggregators (weekly/monthly AI-news), and arXiv paper summaries.

## Purpose

The top-level "AI & ML Research" theme covers everything fundamentally about machine intelligence. Stories that primarily advance the field of AI — new models, training methods, evaluations, agent systems, and theoretical advances — live here. Stories about the **tools, infrastructure, hardware, business, or societal impact** of AI live under their respective top-level themes.

## Sub-Theme Definitions

### 1. Models & Architectures

**What it covers:** New model releases, architecture innovations, scaling laws, foundation model specs, capability claims, model comparisons.

**Examples:**
- Qwen 3.6 release with detailed architecture specs (MoE, context length)
- Gemma 4 uncensored abliteration release
- Mythos model benchmark comparisons
- GPT-5.5 / Claude capabilities discussion
- Scaling laws analysis (chinchilla, compute-optimal)
- New MoE or attention mechanisms
- Model compression / distillation papers

**Overlap guidance:** A model release belongs HERE if the focus is on what the model is and does. If the focus is on practical deployment costs, pricing, or a product launch, it shifts to **Industry & Business** or **Developer Tools**.

---

### 2. Training & Post-Training

**What it covers:** Training techniques, RLHF/DPO/GRPO, fine-tuning methods, synthetic data generation, post-training optimization, reward modeling.

**Examples:**
- GRPO training pipeline improvements
- Multi-Token Prediction (MTP) training method
- RLHF scaling studies
- Synthetic data generation for training
- Fine-tuning efficiency (LoRA, QLoRA comparisons)
- Distillation techniques
- Curriculum learning advances

**Overlap guidance:** A new training method that's general-purpose (applies to any model) goes HERE. A fine-tuning tool (e.g. Axolotl, Unsloth) release goes under **Developer Tools & Infrastructure**. A paper on training dynamics goes under **Papers & Theory** unless it's a practical post.

---

### 3. Benchmarks & Evaluation

**What it covers:** New benchmarks, leaderboards, evaluation methodologies, capability measurements, test sets, model comparison results.

**Examples:**
- Epoch AI domain-specific capability index
- ParseBench leaderboard results
- New benchmark releases (SWE-bench, HumanEval variants)
- Long-context evaluation results
- Multimodal benchmark comparisons
- Evaluation methodology critique or improvement
- Reproducibility studies

**Overlap guidance:** Benchmark results tied to a specific model release can go under **Models & Architectures** instead — use judgment. New benchmark *methodologies* or evaluation frameworks belong HERE.

---

### 4. Agents & Agent Systems

**What it covers:** Agent frameworks, tool use, multi-agent systems, coding agents, agent evaluation, agent harnesses, agent UX and reliability.

**Examples:**
- Codex/Claude Code agent capability discussions
- Agent harness design patterns (context assembly, tool loops, memory)
- Multi-agent coordination research
- Agent benchmarking (SWE-bench, agent-specific evals)
- Prompt injection and safety in agent contexts
- Agent reliability engineering
- MCP (Model Context Protocol) evolution

**Overlap guidance:** Agent FRAMEWORK releases and general agent research go HERE. A specific coding agent *product* launch (e.g. GitHub Copilot feature) goes under **Developer Tools & Infrastructure** if the focus is on the tool/UX rather than the agent science. Agent safety is a gray zone with **Security & Privacy** — put it here if the focus is on architectural solutions, there if the focus is on exploit/policy.

---

### 5. Papers & Theory

**What it covers:** Academic preprints, theoretical advances, novel methods without immediate practical deployment, interpretability research, alignment theory, mathematical ML theory.

**Examples:**
- New attention mechanism paper on arXiv
- Mechanistic interpretability research
- Alignment theory advances
- Information-theoretic ML results
- Novel loss function theory
- Position papers on AI direction
- Interpretability tools (e.g. SAEs, activation patching)

**Overlap guidance:** If a paper ALSO qualifies for another sub-theme (e.g. "Paper on a new training method"), prefer that sub-theme over Papers & Theory. Papers & Theory is the **default bucket** for research that doesn't clearly fit elsewhere, or for papers that are primarily theoretical/mathematical. A paper with a practical implementation or benchmark should go under the relevant practical sub-theme.

---

## Decision Flow for Ambiguous Stories

When a story could fit multiple sub-themes:

1. Identify the story's **primary signal** — what new information does it bring?
   - "New model X released" → Models & Architectures
   - "New way to train models" → Training & Post-Training
   - "New way to measure models" → Benchmarks & Evaluation
   - "New framework for agents" → Agents & Agent Systems
   - "New theoretical insight" → Papers & Theory

2. If primary signal is equally split, ask: **where would someone look for this?**
   - A coding agent paper that introduces both a new architecture AND benchmarks → Agents (primary signal is agent advancement)
   - A training paper with strong theoretical bent → Training & Post-Training (the practical contribution outweighs the theory)

3. If still ambiguous, default to the **earliest logical sub-theme** in the numbered list above.

## Usage Across Skills

| Skill | Sub-theme Application |
|-------|----------------------|
| hn-brief-digest | Group HN stories under AI & ML Research into sub-theme subsections when 3+ stories share a sub-theme |
| x-digest | Tag tweets with sub-theme in addition to top-level theme |
| smol.ai news (weekly/monthly) | Classify AI news items into sub-themes for granular reporting |
| arxiv-daily-papers | Assign arXiv papers to sub-themes for themed paper grouping |

---

*Part of the unified cross-platform theme system. First defined: 2026-05-18.*
