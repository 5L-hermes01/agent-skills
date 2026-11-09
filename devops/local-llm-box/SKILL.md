---
name: local-llm-box
description: Operate local LLM box; probe, attribute, swap models.
version: 0.1.0
author: Hermes Agent 01
license: Apache-2.0
metadata:
  hermes:
    tags: [local-llm, litellm, llama.cpp, qwen, inference, probes]
    related_skills: [waytoagi-reader]
---

# Local LLM Box Operations

## When to Use

Any task against the local inference box: choosing/verifying a model id,
diagnosing timeouts or slow responses, attributing which caller generates
traffic to a model, or upgrading a pipeline to a newer model family.

Topology: LiteLLM proxy listens on 192.168.100.10:11434 (identical to
host.containers.internal:11434 from the Hermes container; DNS name
lunarbeacon.newyork.nicklange.family) and routes to llama.cpp at
http://llama-cpp:1235/v1. All models register as `openai/...` ids;
aliases (e.g. `qwen3.8`, `qwen3.5-35b-a3b`) are thin named entries and
may map to slow or broken files.

## Discovering state
- `GET /v1/models` — registered ids (aliases + explicit variants).
- `GET /health` — LiteLLM per-endpoint status. An unhealthy row naming a
  model that does not exist on llama.cpp = junk model group in the proxy
  config (remove it).
- `GET /model/info` — each model group's backend routing.

## The one rule: probe explicit ids, never trust aliases

Alias hangs are real: `qwen3.8` alias took ~70s/no response while explicit
`qwen3.8-27b-instruct-mtp-d3` answered in ~3-21s cold. Always:
1. Pick the EXPLICIT variant id you intend to use.
2. Send a tiny completion (max_tokens ≤ 16) with a generous curl -m,
   and TIME it.
3. Wire clients only to ids that answer fast; >30s = reject.

Script: `scripts/probe_models.py` runs this over a candidate list.
Model list lives in `scripts/probe_models.json` — edit THAT file to
change defaults without touching code.

## Attributing model traffic
- Scheduled jobs: /opt/data/cron/usage_audit.jsonl logs every cron run
  (ts, job_id, model, error). Grep by model id to count calls/timeouts
  per job. Clean audit = the volume is not coming from Hermes crons.
- Direct LAN clients (other apps/devices hitting :11434) are INVISIBLE
  from inside the Hermes container: no docker socket, no LiteLLM
  spend-log access. To identify them, on the host:
  `docker logs <litellm-container> | grep <model-id>` for client IPs/
  timestamps.

## Swapping model versions
- The box holds families in parallel (Qwen 2.5/3.5/3.6/3.8 + Gemma-4):
  deploying a new version = repointing client configs, not downloading.
- Prefer the MTP/drafter build of a series for latency-sensitive
  pipelines (e.g. `qwen3.8-27b-instruct-mtp-d3`).
- Clients that embed the model id in cache keys (e.g. WaytoAGI
  translation v2 cache) lose cache once per switch — expected, let
  it warm.

## Pitfalls
- Cron manager: the action to un-pause is `resume` — there is no
  `unpause`; `update` accepts only known fields (no bare `enabled`).
- Hermes refuses agent edits to config.yaml (security). Fix provider
  defaults by handing the user the command:
  `hermes config set providers.<name>.default_model <id>` (or manual
  yaml edit). Never fight the guard with sed/echo.
- Multi-model GGUF box: each request swaps weights per target model.
  Big files (e.g. 35B Q4_K_M) cold-load behind other requests and cause
  client-side timeouts. Persistent timeouts with a correct, fast-probing
  id ⇒ inspect load/swap behavior on the host, not the client.
- Model lists belong in config files, not in script code. The
  probe_models.py script loads its model list from probe_models.json.
  Change the JSON, not the Python.
