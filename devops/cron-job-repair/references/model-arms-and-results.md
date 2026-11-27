# Model arms and measured results (this host, 2026-11-23)

Arms live in `scripts/cron-model-bench.py`. Every row below is a **real cron run**
with delivery forced to `local`, harvested from `cron/usage_audit.jsonl`.

- `default` — `--unpin --provider nous` → `deepseek/deepseek-v4.1-flash`
- `qwen` / `inkling` — the local box (`ollama-qwen3.6:27b` provider, 11434)
- `qwen37f` — `qwen/qwen3.7-flash` (nous), $0.030 in / $0.130 out per M
- `hy4flash` — `tencent/hy4-flash` (nous), $0.035 in / $0.140 out per M
- `v41batch` — `deepseek/deepseek-v4.1-flash:batch`, $0.050 / $0.150

## Why prompt_tokens is the number that matters

These jobs are input-dominated: a single run pushes 0.8M–3.7M prompt tokens and
produces 5k–60k completion tokens. Input price decides the bill; a
reasoning-mandatory model quietly loses on output.

## Measured per job (duration, tokens, verdict)

| job | default | cheap arm that worked | cheap arm that failed |
|---|---|---|---|
| Daily Open Work Reminder | 24.8s · 156k/3.7k | **qwen3.7-flash 16.5s · 66k/1.2k** ✓ | — |
| WaytoAGI Daily | 41.4s · 248k/5.7k | **qwen3.7-flash 112s · 256k/8.6k** ✓ (28KB digest, 6/6 items); hy4-flash 48s · 162k ✓ (10KB, leaner) | — |
| daily-ai-news | 180.8s · 1.14M/21k | **hy4-flash 124.6s · 800k/17k** ✓ (delivered the stale-source NOTE) | qwen3.7-flash: 1.5KB meta-summary with markdown ✗ |
| x-weekly-digest | 559s · 3.44M/59k | **hy4-flash 340s · 2.49M/36k** ✓ (9.1KB real digest) | qwen3.7-flash: 978B "Run complete. Here's the summary:" ✗ |
| weekly-ai-news | 465s · 3.75M/49k ✓ | none | qwen3.7-flash `silent=True` 30s/180k; hy4-flash `silent=True` 45s/89k ✗✗ |
| local qwen (all heavy jobs) | — | WaytoAGI Weekly 215s · 697k/3k ✓ | weekly-ai-news/x-weekly/daily-ai-news: 25-min timeouts ✗ |
| local inkling | — | nothing | context ceiling on every large job; `qwen3.8-flash-next` fails to load (HTTP 500) ✗ |

## The prompt contract fixes both cheap-model failure modes

Observed before and after adding an OUTPUT CONTRACT to the prompt (first line is
the deliverable, no report of what was read or processed, `[SILENT]` only for a
verified empty period):

| job | before hardening | after hardening |
|---|---|---|
| weekly-ai-news × qwen3.7-flash | `silent=True` 30s / 180k tokens, nothing sent | 252s / 1.0M tokens, 22.8KB real roundup |
| weekly-ai-news × hy4-flash | `silent=True` 45s / 89k tokens, nothing sent | 58.5s / 191k tokens, honest one-line failure report |
| x-weekly-digest × hy4-flash | 340s / 2.49M tokens, 9.1KB digest | 266s / 1.73M tokens — contract also cut tokens 30% |

So a cheap model is not automatically unusable: it is unusable *until the prompt
names the deliverable and closes the escape hatches*. Harden first, then bench,
then pin.

## Cost per run where the swap works: reminder $0.0021 (8.8x cheaper), daily-ai-news
$0.030 (5.7x), x-weekly-digest $0.092 (4.3x), WaytoAGI Daily $0.0064–0.0088
(3.3–4.6x). Whole broken set: ~$2/mo instead of ~$8.9/mo.

## Failure modes a cheap model shows (all report `ok`)

1. **Narration.** Final response is *about* the work — "Run complete. Here's the
   summary:", counts of items processed — instead of the deliverable. 978B where
   the job normally emits 22KB. Fix the prompt: the first line must be the
   deliverable, and forbid any report of what was read or processed.
2. **Silent no-op.** The prompt offers `[SILENT]` for the empty case; a weak model
   takes that exit after a partial read. Job reports `ok` in a fraction of the
   usual tokens and delivers nothing. Fix the prompt: reserve `[SILENT]` for a
   *verified* empty period where the data script printed a zero item count.
3. **Context ceiling.** `conversation has grown too long for <model> to read` —
   the local box's usable context is far below the 1M its catalogue claims.
4. **`response_silent` and output size are the real pass/fail signals.** Duration
   and exit code are not: the worst outcome here was a 30-second "success" with
   nothing delivered.

## `:batch` variants are not usable for cron on this account

`deepseek/deepseek-v4.1-flash:batch` answered 3/3 interactive probes (23–26s) and
404'd on 2/2 real cron runs (`Couldn't find that, sorry`). Cheap-looking suffix,
broken on the path that matters — bench it in the real path before believing the
price sheet.

## Local alias gotcha

The provider pins `qwen3.8-27b-instruct`; `qwen3.8-27b-instruct-mtp` and
`qwen3.8-27b-instruct-mtp-d3` also serve. During the box's ROCm/Unsloth restarts,
completions hang for minutes while `/v1/models` still answers 200 — a hang is not
proof of a broken alias, and 1235/8000/11434 can disagree about being up.
