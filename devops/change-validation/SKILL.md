---
name: change-validation
description: After any skill change, capture validation specs and validate the next run — triage failures before escalating to user.
version: 1.0.0
author: Hermes Agent 01
license: MIT
metadata:
  hermes:
    tags: [validation, quality, triage, post-change]
---

# Change Validation Skill

After we modify any skill, we must validate the next run against a captured spec of "what good looks like." This skill standardizes that workflow across all skills.

## When to Use

Load this skill immediately after completing ANY skill change that affects output behavior (format, content, delivery). Skip for pure bugfixes or internal refactors that don't change user-visible output.

## Workflow

### Step 1: Capture the Spec

After the change is complete and we've seen at least one good trial run, create a validation spec:

1. Create `references/validation-spec.md` inside the affected skill's directory
2. Use the template below — be concrete and testable
3. Include both positive signals (what MUST be present) and negative signals (what MUST NOT be present)
4. Save it via `skill_manage(action='write_file', name='<skill>', file_path='references/validation-spec.md', file_content='...')`

### Step 2: Register for Validation

Add an entry to this skill's registry so we remember to check:

1. Read `references/validation-registry.json` in THIS skill's directory
2. Add or update the skill's entry: `{"skill": "<name>", "root": "<repository-relative skill directory>", "last_change": "<ISO date>", "spec": "references/validation-spec.md", "last_validated": null, "last_result": null}`
3. Write it back

### Step 3: Validate at Next Run

When the affected skill's cron job fires or the user runs it manually:

1. Load the validation spec at `<repository>/<root>/<spec>` from the registry entry
2. Capture the actual output
3. Compare against every MUST and MUST NOT in the spec
4. Record pass/fail for each criterion
5. Update that entry's `last_validated` to the ISO timestamp of this run and `last_result` to `"pass"` or `"fail"`. Repeat after each triage re-run; never mark an unexecuted check as passed.

### Step 4: Triage on Failure

If ANY check fails:

1. **Diagnose first** — check logs, API responses, state files, config changes. Do not guess.
2. **Fix if straightforward** — typo, format regression, missing field. Patch and re-run.
3. **PR if structural** — logic error, API change, scope creep. Branch, fix, PR.
4. **Escalate only when stuck** — blocked on external dependency, ambiguous spec, needs user decision.

Do NOT ask the user "is this OK?" before doing triage. Only escalate after you've attempted diagnosis and have a concrete finding or recommendation.

**Remote-resource safety**: If the skill involves remote API calls or external resources, do as much local diagnosis as possible first (check logs, state files, cached data, config). Escalate for explicit permission before making any remote calls during triage — repeated diagnostic API calls can overwhelm external systems, get credentials rate-limited, or trigger abuse thresholds.

### Step 5: Update the Spec

If the spec was wrong (too strict, missed a valid variant), update it. The spec is living documentation, not a contract.

## Spec Template

```markdown
# Validation Spec: <skill-name>
# Last updated: <ISO date>
# Change: <brief description of what changed>

## Positive Checks (MUST be present)

- [ ] <concrete, testable assertion>
- [ ] <e.g. "Header line contains target OTD price like '$58,451'">
- [ ] <e.g. "Table has exactly 5 columns: Dealer (mi), Price, Δ, Color, C/O">

## Negative Checks (MUST NOT be present)

- [ ] <concrete, testable assertion>
- [ ] <e.g. "No 'Top 5 Cheapest' or 'Cheapest Deals' section">
- [ ] <e.g. "No inline URLs inside table rows">

## Format-Specific Checks

- [ ] <platform-specific checks, e.g. Signal message length, Discord embed limits>
```

## Registry Format

`root` is relative to the repository root; `spec` is relative to that skill directory. `references/validation-registry.json`:
```json
{
  "skills": [
    {
      "skill": "car_tracker",
      "root": "research/car_tracker",
      "last_change": "2026-07-27",
      "spec": "references/validation-spec.md",
      "last_validated": null,
      "last_result": null
    }
  ]
}
```

## Memory Note

After registering, save a memory note so the agent remembers to validate at next delivery:
- Format: "VALIDATE: <skill> — check against references/validation-spec.md at next run"
- The agent loads this skill, reads the spec, and validates.
