# Delegate to Antigravity

Use this handoff for every implementation task. Fill every field from the task and verified analysis; do not invent missing facts.

## Prompt source gate

The prompt must be composed by Codex from:

1. the approved `.codex/plans/master-plan.md`,
2. exactly one `.codex/tasks/TASK-###.md` or `FIX-###.md`, and
3. current verified state/evidence.

The task must be `READY` and its dependencies must be satisfied. Save the exact rendered prompt as `.codex/evidence/handoff-<TASK-ID>.md` before transmission. Include `SOURCE PLAN`, `SOURCE TASK`, and `GENERATED AT` metadata. If any source is missing/stale or the task is not READY, do not type into Antigravity; mark `HANDOFF_BLOCKED` and return to planning.

Prefer the deterministic renderer in `.agents/commands/prepare-handoff.md`; record its SHA-256 in the handoff evidence and reject any prompt text that differs from the rendered file.

```text
TASK ID:
TASK TITLE:
OBJECTIVE:
CURRENT STATE:
RELEVANT FILES:
ROOT CAUSE:
REQUIRED CHANGE:
DO NOT CHANGE:
IMPLEMENTATION CONSTRAINTS:
ACCEPTANCE CRITERIA:
TEST COMMANDS:
UI/UX VERIFICATION:
COMPUTER USE INSTRUCTIONS:
EXPECTED OUTPUT:
REPORT FORMAT: use .agents/skills/antigravity-worker/SKILL.md
```

When Computer Use is available, use `.agents/skills/computer-use-qa/SKILL.md` to launch/focus Antigravity, open the intended repository, confirm branch/workspace, send the complete handoff using the accessibility/screenshot input ladder, verify a visible task marker before sending, confirm acknowledgement by TASK ID, and capture raw text/screenshot evidence. If Computer Use is unavailable, write `COMPUTER_USE_UNAVAILABLE`; if the Agent composer cannot be targeted, write `HANDOFF_INPUT_UNAVAILABLE`. In either case do not claim delegation. Antigravity must report changed/created/deleted files, summary, commands/tests/results, limitations, blockers, and remaining UI checks.

If Antigravity cannot be reached, stop the delegation attempt. Ask for the capability to be restored or explicit user authorization for a separately labelled Codex-owned implementation task; never relabel Codex work as Antigravity work.
