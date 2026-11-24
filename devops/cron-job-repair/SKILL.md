---
name: cron-job-repair
description: Use when a cron job fails. Classify cause, repin, verify.
version: 1.0.0
author: Hermes Agent 01
license: MIT
metadata:
  hermes:
    tags: [cron, repair, models, delivery, benchmark]
---

# Cron Job Repair

## When to Use

- A scheduled job shows `last_status: error`, a `failure_streak`, or has stopped
  producing output.
- `hermes cron doctor` reports failing jobs or "finished but the result was not
  delivered".
- A model a job is pinned to was retired, lost credits, or was replaced.
- You are choosing between a hosted and a local model for a scheduled job and
  need measured timings, tokens and a cost estimate before pinning.

Repair a broken Hermes cron job: find it, classify it, fix the real cause, prove it
ran. Job prompts are not the usual culprit — model pins, delivery targets and
scripts are.

## 1. Audit

- `hermes cron doctor` — flagged jobs with the failure text already attached.
- `/opt/data/cron/jobs.json` — per job: `last_status`, `failure_streak`,
  `last_error`, `model`, `provider`, `model_snapshot`, `provider_snapshot`,
  `deliver`, `next_run_at`, `enabled`. `model: None` + a `model_snapshot` means
  the job is unpinned and took the snapshot from config at fire time.
- `/opt/data/cron/usage_audit.jsonl` — one row per run: `ts`, `job_id`, `model`,
  `duration_ms`, `prompt_tokens`, `completion_tokens`, `response_silent`,
  `deliver_target`, `error`. **Timings and tokens live here**, not in the job
  record.
- `/opt/data/cron/{executions,deliveries}.db` — durable attempt + delivery rows.
- `hermes cron runs <job_id>` — last attempts with their error text.

## 2. Classify (the six real causes)

1. **Pin retired / out of credits** — `HTTP 404 … requires available credits`,
   `model not found`. Fix: `hermes cron edit <id> --unpin` (rides
   `model.default` from config.yaml) or pin a model that exists *and* has balance.
2. **Unpinned job lands badly** — `HTTP 429 … fair-share rate limit`: the
   snapshot resolved to a throttled free model. Same fix, with an explicit pin.
3. **Context ceiling** — `conversation has grown too long for <model> to read`.
   One conversation exceeded that model's context. Local deployments are the
   usual victims (small `n_ctx`); fix the prompt's per-turn read volume or pick a
   bigger-context model. Probe before blaming: a 30k-token prompt that succeeds
   bounds the limit from below.
4. **Delivery target dead** — `Could not resolve '<name>' on <platform>` or
   `live adapter delivery … failed: RPC send failed`. The group/channel was
   renamed. Fix: `hermes send --list <platform>` prints every current target;
   use the exact name, then `hermes cron edit <id> --deliver <target>`.
5. **Script failure** — `Script exited with code 1`. Nothing to do with any
   model: read the captured stderr in the job record and fix the script. Keep
   script jobs (`--no-agent`) separate from LLM jobs in your head — they cannot
   be fixed by changing models.
6. **Silent-but-fine vs silent-but-empty** — a job can finish `ok` and still
   never deliver (`last run finished but the result was not delivered`). An LLM
   that narrated instead of emitting `[SILENT]`, or emitted empty output, looks
   identical in `last_status`.

## 3. Repair rules

- **Snapshot first:** `cp cron/jobs.json cron/jobs.json.bak-$(date +%s)` —
  `hermes cron edit` writes in place and you will be restoring more than once.
- **Verify the replacement model answers before pinning it:** a 4-token
  `chat/completions` call against the provider. A pin to a nonexistent model
  fails silently until the next scheduled fire.
- **Verify a repaired job by running it, never by reading the file:**
  `hermes cron edit <id> --deliver local --failure-deliver local` →
  `hermes cron run <id>` → confirm a **new** row in `usage_audit.jsonl`
  (`error: null`, sane `duration_ms`) → restore the real delivery target.
  `local` delivery means verification never posts to Signal/Discord.
- **Check `response_silent` and the output size, not just the exit code.** A model
  swap can turn a job into a silent no-op: a cheap model read a prompt that says
  "respond `[SILENT]` if there is nothing to report", skipped the work, and finished
  `ok` in 30s using a twentieth of the usual tokens with `response_silent: true`.
  Exit status said success; nothing was delivered. A job that normally produces a
  large digest is only fixed when it produces a large digest again.
- `hermes cron run` may exit non-zero while still having fired — the audit row is
  the truth, not the exit code. Wait on the log, not the command.
- Model cold-load on a local box can add minutes to a run; a run that looks
  hung is often just loading weights.
- Unpinned is the resilient default: it rides `model.default`, so retiring a
  model is a one-line config change instead of an edit per job.

## 4. Cost a model choice before committing to it

- Live prices (per token): `curl -s https://inference-api.nousresearch.com/v1/models`
  → `pricing.prompt` / `pricing.completion` / `pricing.input_cache_read`.
  Prices are absent from the docs model catalog — the API is the source.
- Real per-run tokens from `usage_audit.jsonl`; multiply by price, then by
  cadence. `prompt_tokens` is the **sum over all turns**, not one context, so a
  job can total >1M tokens while every individual turn fits inside 1M.
- Local inference is $0/token; it costs wall-clock and quality instead. Judge a
  local model on the **delivered text**, not on a clean exit: a model that
  miscounts or leaks its reasoning into a phone-facing digest is a worse
  outcome than paying a fraction of a cent.

## 5. Benchmark across models

`scripts/cron-model-bench.py --jobs <id>,<id> --arms default,qwen,inkling`
edits each job to an arm, forces a real run with delivery suppressed, harvests
duration/tokens/error from the audit log, restores the job, and appends to
`/opt/data/cache/cron-model-bench/results.jsonl` (resumable — pairs already
captured are skipped). Arms are defined in the script's `ARMS` dict.

## References

- `references/model-arms-and-results.md` — this host's arms, measured results
  and the verdict per job.
