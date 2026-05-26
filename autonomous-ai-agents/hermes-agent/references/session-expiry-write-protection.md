# Session-Expiry Write Protection

## Problem

When generating code changes in conversation (patches, new files, skill updates), the agent presents the code to the user for approval in an assistant message. If the session expires (idle timeout, /new, conversation switch) between the assistant message and the actual `write_file`/`patch` tool calls, the changes exist **only in chat history** — they are lost permanently because the tool calls never executed.

Root cause: the agent's natural workflow is "generate → present → confirm → write", but the "write" step is the only one that persists to disk. If the session ends before "write", all prior work is lost.

## Fix

Write changes to disk FIRST, then present confirmation. Reverse the order:

### Before (broken)
```
1. Generate code changes in assistant message
2. Present to user for approval ("Here's what I'll do...")
3. Wait for user confirmation
4. [RISK: session expires here → code lost]
5. Call write_file/patch/skill_manage
```

### After (safe)
```
1. [Optional: state intent briefly — "Adding tweets command now"]
2. Call write_file/patch/skill_manage immediately
3. Present confirmation with what was written
```

## Corollary: No Approval Gating

Do not hold file writes hostage waiting for user approval or confirmation. The user's message is their approval. If they said "add the tweets command", write it immediately and confirm after. If they need changes, they'll tell you — and you patch then.

The exception: destructive operations (deleting files, removing features) where user confirmation is legitimately needed.

## Check: are files on disk matching the conversation?

At the end of any session that produced code changes, verify:
1. The files you intended to change were actually written (check timestamps or content)
2. No planned patch/write_file calls remain pending in the message log

This is especially critical on Discord/Signal where sessions are ephemeral and the user may switch contexts without warning.

## Related

- The nightly-repo-sync script at `/opt/data/scripts/nightly-repo-sync.py` only syncs `/opt/data/skills/` — scripts in `/opt/data/scripts/` are NOT in any repo and exist only on local disk. They are uniquely vulnerable to session expiry.