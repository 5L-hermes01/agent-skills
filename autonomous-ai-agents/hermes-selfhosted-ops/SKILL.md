---
name: hermes-selfhosted-ops
description: "Operate a self-hosted Hermes deploy: s6, config, profiles."
version: 0.1.0
author: Hermes Agent 01
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [hermes, deployment, s6, docker, profiles, config, multimodal]
    related_skills: [nightly-upstream-sync, change-validation]
---

# Hermes Self-Hosted Ops Skill

Operating and extending a self-hosted Hermes deployment in an s6-supervised container.
Covers what the public docs get wrong for this deployment shape, and the failure modes that
silently do nothing instead of erroring. Not about installing Hermes — about not breaking it.

## When to Use

- Restarting, reloading, or debugging a running Hermes gateway in a container deploy
- Creating, configuring, or deleting a Hermes profile
- Enabling a messaging platform, toolset, or feature and needing it to actually take effect
- Standing up a second agent instance that must talk to the first
- Anything multimodal (speech, image, video) that "should work but doesn't"
- Don't use for: writing a new skill's content (`hermes-agent-skill-authoring`)

## Prerequisites

- `s6-svc` / `s6-svstat` on PATH, or under `/command/`
- `hermes` CLI on PATH; install tree known (`/opt/hermes`, venv at `/opt/hermes/.venv`)
- Know which profile you are targeting. All commands take `-p <profile>`; without it you hit the
  default profile.
- Never print a credential value. `.env` is secrets; `config.yaml` is settings.

## How to Run

```
terminal(command="hermes gateway status", timeout=30)          # but read Pitfalls first
terminal(command="hermes -p <profile> config get <key>", timeout=30)
terminal(command="hermes -p <profile> config set <key> <val>", timeout=30)
```

## Quick Reference

```
s6-svc -r /run/service/gateway-<profile>     # correct gateway restart
ls /run/service/                             # all supervised services
hermes profile create <name> [--description "…"]   # no --clone for least privilege
hermes profile delete <name> -y              # also removes wrapper + s6 service
hermes profile list                          # profile, model, gateway, distribution
hermes config set | unset | get <key>        # use unset for removals, never hand-edit
hermes [-p <p>] doctor                       # toolset availability + auth state
hermes -p <p> tools list                     # per-platform enabled toolsets
```

## Procedure

1. **Restart a gateway** → check supervision before touching it.
   `/run/service/gateway-<profile>/run` reveals the real invocation. Restart with
   `terminal(command="s6-svc -r /run/service/gateway-<profile>", timeout=30)`.
   Completion criterion: `s6-svstat` reports up and the gateway comes back within seconds.
   If s6-svc is not on PATH, look under `/command/`.

2. **Create a profile** → `hermes profile create <name> --description "…"`.
   It auto-registers `/run/service/gateway-<name>/` with a `down` file (will not auto-start) and
   writes a wrapper at `$HERMES_HOME/home/.local/bin/<name>`. Do not hand-write service dirs.
   Completion criterion: `hermes profile list` shows it.

3. **Give a profile credentials** → profiles are isolated islands with their own `.env` and
   `auth.json`. Extract key lines programmatically and append; never echo a value.
   Completion criterion: `hermes -p <name> doctor` shows the expected auth provider logged in.

4. **Constrain a profile's tools** → set `platform_toolsets.<platform>` as an explicit allow-list.
   List every toolset the profile needs; anything omitted is unavailable. Young toolsets
   (`video`) are absent from defaults and must be named explicitly.
   Completion criterion: `hermes -p <name> doctor` lists the toolsets with no unexpected `⚠`.

5. **Enable a platform** → write `platforms.<name>.enabled: true` at the TOP level, then reload the
   gateway. Completion criterion: inbound messages route, and the adapter reports connected.

6. **Verify every config write** by reading the file back — see Pitfalls on the false warning.
   Completion criterion: the value round-trips.

## Pitfalls

- **`hermes gateway status` misreports supervised gateways.** It prints "Running manually, not as
  a system service" for a gateway that IS s6-supervised. Trusting it leads to killing the process
  and relaunching by hand, which fights the supervisor. Always check the parent process and
  `/run/service/` before restarting.

- **Platform enable flags live at TOP-LEVEL `platforms:`,** not `gateway.platforms:` as some docs
  show. The gateway loader reads `config["platforms"]`. Writing to `gateway.platforms` is a silent
  no-op. Confirm against the existing `platforms:` block in the config.

- **`hermes config set` prints "⚠ not a recognized config key" for valid keys** in a newly created
  profile — it validates against that profile's own thin YAML, not `DEFAULT_CONFIG`. Values are
  written correctly. Verify by reading the file back rather than trusting the warning. Corollary:
  a saved value can still be inert if the key genuinely does not exist — check `DEFAULT_CONFIG`
  in the source for anything load-bearing.

- **The consumption dir is rebuilt nightly.** `$HERMES_HOME/skills/` is cleared and rebuilt from
  an upstream clone plus a repo of originals. Skills created only in the consumption dir are
  deleted at the next rebuild. The durable home is the repo tree
  (`/opt/data/repos/agent-skills/<category>/<name>/`); the sync commits new files, opens a PR, and
  overlays them back. Commit directly to the repo's `main` only if you push before the rebuild
  (it runs `git reset --hard origin/main`).

- **`video_analyze` exists but is opt-in.** It is a real tool (`toolset="video"`), absent from every
  default `platform_toolsets` list, and absent from the docs index (which lists only video
  *generation*). If `video` is not explicitly listed, video input silently does not exist.

- **STT and TTS default to provider `openai`.** With no OpenAI key both are dead — speech in and
  speech out. Non-key alternatives: `local` (faster-whisper, a lazy dep that auto-installs),
  `edge` (no key), plus gemini/xai where a key exists. Check `hermes status` for the OpenAI line
  before assuming voice works.

- **`a2a (system dependency not met)` in `hermes doctor` is not a missing package.** It is the
  fail-closed config gate: the toolset serves only when `a2a_agents` is configured, `A2A_PORT` is
  set, or `platforms.a2a.enabled` is true. Configuring any peer clears it.

- **`hermes profile create --clone` copies `.env` — every secret — plus skills and config.** For a
  profile that will be used by an untrusted party, clone is the wrong tool: build clean and
  allow-list toolsets instead.

- **`--clone` / `--clone-all` differences matter:** `--clone` takes config + `.env` + SOUL +
  skills; `--clone-all` additionally takes state. Neither takes per-profile history.

- **Same-machine agent-to-agent is NOT `delegate_task`.** Delegation is in-process and
  single-profile. Crossing to another profile means another `HERMES_HOME` and process, so use A2A,
  the API server (`/p/<profile>/…`), or a webhook.

- **Inbound A2A tasks inject into a live gateway session of the serving profile.** The serving
  profile's gateway must be running, and it must have whatever rule is needed to act on the
  escalation always visible — a skill that loads only on demand may never fire.

## Verification

- `s6-svstat /run/service/gateway-<profile>` reports the service up after a restart
- `hermes profile list` shows exactly the profiles you expect, with the right gateway state
- `hermes -p <profile> doctor` shows no unexpected toolset warnings and the expected auth provider
- Every `config set` round-trips through `config get`
- For a restricted profile: no `terminal`, `file`, `browser`, or `code_execution` tool appears in a
  live session
- After the next nightly rebuild, the skill still resolves via `skills_list`
