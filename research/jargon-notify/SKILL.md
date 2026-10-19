---
name: jargon-notify
description: Poll the jargon registry for new terms and post them to a Discord channel. Maintains a git-tracked state file so only genuinely new terms trigger notifications.
version: 1.0.0
author: Hermes Agent 01
license: MIT
metadata:
  hermes:
    tags: [jargon, notify, discord, automation, cron]
    related_skills: [jargon, unified-digest-themes]
---

# Jargon Notify

Watches the jargon registry for new terms and posts kindergarten-level definitions to a designated Discord channel. Designed to run as a cron job — stateless between runs, with all tracking in a git-committed state file.

## Run Mode (deterministic — converted 2026-10-18)

The live cron job (`4a5569eca2b5`, every 4h) runs **no_agent** with
`/opt/data/scripts/jargon_notify.py` — no LLM, no tool loop, no skill load.
Behavior: registry+state+blocklist loaded from disk, set-difference, new terms
posted via `hermes send` to Discord, state atomic-written to both mirrors.
**Empty stdout = silent success** (scheduler suppresses delivery); non-zero
exit = failure alert is delivered. `--dry-run` and `--self-test` flags exist;
`JARGON_REGISTRY`/`JARGON_STATE`/`JARGON_BLOCKLIST` env vars redirect paths for
tests. Do NOT reimplement this workflow with write_file scratch helpers —
that caused 745+ runs of recurring "file edit FAILED" warnings (scratch
overwrite refusals on a pre-existing helper) before the conversion. State JSONs
are deliberately gitignored; /opt/data is the persistent mount — no git step.
The agent workflow below is legacy fallback documentation only.

## Architecture

```
Registry (write source)      State file (read source)      Discord (output)
        │                           │                          │
┌───────▼────────┐          ┌───────▼──────────┐       ┌───────▼──────┐
│ jargon-registry │          │ posted-terms.json │       │ channel ID   │
│ .json           │          │ (git-tracked)     │       │ 15151903...  │
└───────┬────────┘          └───────┬──────────┘       └───────▲──────┘
        │                           │                          │
        └───────────┬───────────────┘                          │
                    │ DIFF                                      │
              ┌─────▼─────┐                                    │
              │ NEW TERMS? │──── yes ────► format + post ───────┘
              └─────┬─────┘
                    │ no
                 [SILENT]
```

## State File

Location: `<jargon-skill>/references/posted-terms.json`

```json
{
  "version": 1,
  "last_checked": "2026-06-13T18:00:00Z",
  "posted_terms": {
    "BERT": "2026-06-13T18:00:00Z",
    "DPO": "2026-06-13T18:00:00Z"
  }
}
```

Each entry maps `term` → ISO timestamp when it was first posted to Discord. Terms not in this map are "new" and trigger a notification.

## Workflow

### Step 1: Load both sources

Load the jargon registry from the consumption directory:
```
/opt/data/skills/research/jargon/references/jargon-registry.json
```

Load the posted-terms state from the agent-skills repo (primary source of truth):
```
/opt/data/repos/agent-skills/research/jargon/references/posted-terms.json
```

If the state file doesn't exist (first run), create it with an empty posted_terms object and seed it with whatever terms are in the registry.

### Step 2: Diff

```python
import json, os
registry_terms = set(registry["terms"].keys())
posted_terms = set(state["posted_terms"].keys())
# Exclude terms the user has marked as known (jargon-blocklist.json)
blocklist_path = "/opt/data/skills/research/jargon/references/jargon-blocklist.json"
blocked = set()
if os.path.exists(blocklist_path):
    blocked = set(json.load(open(blocklist_path)).get("blocked_terms", []))
new_terms = (registry_terms - posted_terms) - blocked
```

If no new terms: [SILENT] — do nothing, do not send any message. Exit. (Blocked terms in jargon-blocklist.json are excluded from new_terms even when absent from state.)

### Step 3: Post new terms to Discord

For each new term, extract the kindergarten-level plainspeak definition from the registry entry:
```
registry["terms"][term]["plainspeak"]["kindergarten"]
```

Format as a Discord message:
```
🆕 New jargon: **TERM** — Full Name — kindergarten-level explanation
```

Example:
```
🆕 New jargon: **VPO** — Vector Policy Optimization — Teaching AI to come up with lots of different good ideas instead of just one
```

Post using the Hermes CLI — there is no in-tool `send_message` available in cron/headless mode:

```bash
hermes send --to discord:jargon-watch "🆕 New jargon: **TERM** — Full Name — kindergarten-level explanation"
```

Channel `discord:jargon-watch` resolves to `discord:1515190329832374272`. Group all new terms into a single message (one term per line). If more than 10 new terms, split into multiple messages. Check the command exit code (0 = delivered) before marking terms as posted.

### Step 4: Update state file

Add each newly posted term to `posted_terms` with current ISO timestamp. Update `last_checked`.

Write the updated state to BOTH locations:
1. `/opt/data/repos/agent-skills/research/jargon/references/posted-terms.json` (git repo, primary)
2. `/opt/data/skills/research/jargon/references/posted-terms.json` (consumption dir, immediate availability for next cron run)

### Step 5: Commit to git

Commit the updated state file in the agent-skills repo:
```bash
git -C /opt/data/repos/agent-skills add research/jargon/references/posted-terms.json
git -C /opt/data/repos/agent-skills commit -m "jargon-notify: posted N new terms to Discord"
```

Use `5L-hermes01` identity (user.name = "5L-hermes01", user.email = "hermes1@5l-labs.com").

Push is optional — the nightly sync script will pick it up and push with any other changes.

## Cron Job

Schedule: every 4 hours (can be tightened or relaxed)

```
cron: 0 */4 * * *
skills: [jargon-notify]
prompt: Run jargon-notify workflow to check for new jargon terms and post them to Discord.
deliver: origin
```

The cron prompt is intentionally minimal since the skill encodes all the logic.

### Dry-run mode

Set to `deliver: local` instead of `origin` to test without notifying the user. The cron still posts to Discord but the job output goes to local files only.

## Dependencies

- **jargon skill**: must have `jargon-registry.json` in its references directory
- **send_message tool**: required for Discord posting (available by default)
- **write_file tool**: required for state file updates
- **terminal tool**: required for git commits
- **agent-skills repo**: must be cloned at `/opt/data/repos/agent-skills/` with git identity configured

## Discord Channel

Default: `discord:1515190329832374272`

To change, update the send_message target in Step 3.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| No new terms | [SILENT] — no message, no git commit |
| State file missing | Create seeded with all current registry terms (no notification) |
| Registry missing | Error — log and exit, don't touch state |
| Registry term deleted | Nothing — we only detect additions, not removals |
| Discord send fails | Log error, don't update state (term will retry next run) |
| Git commit fails | Non-fatal — state file is still written, nightly sync will pick it up |
| Consumption dir stale | State is read from agent-skills repo as primary source of truth |

## Pitfalls

- The consumption directory (`/opt/data/skills/`) is rebuilt nightly from upstream + agent-skills originals. Writing state to the consumption dir is a convenience copy — the agent-skills repo holds the real state.
- New terms enter the registry via digest pipelines (x-digest, hn-brief-digest, arxiv). If those pipelines aren't running, no new terms will appear here.
- The registry uses the term acronym as the JSON key (e.g., `"BERT"`, not lowercase). The diff is case-sensitive — `"Bert"` won't match `"BERT"`.
- If a term is added to the registry and the cron fires before the state file diff picks it up, no problem — it'll get posted on the next tick.

## Version History

- 1.0.0 (2026-06-13): Initial skill. Polls jargon registry, diffs against git-tracked posted-terms.json, posts new terms to Discord.
