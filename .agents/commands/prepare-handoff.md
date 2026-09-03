# Prepare Codex handoff

Generate the Antigravity prompt only from the approved plan and one task:

```text
python .agents/skills/codex-orchestrator/scripts/render_handoff.py \
  --plan .codex/plans/master-plan.md \
  --task .codex/tasks/TASK-003.md \
  --output .codex/evidence/handoff-TASK-003.md
```

The renderer refuses tasks whose `STATUS` is not `READY`, records source paths/time/hash, and includes the task's objective, scope, acceptance criteria, tests, and UI checks. Review the generated file, then use it as the exact text for Computer Use transmission. Never edit the rendered prompt after hashing; regenerate it if the plan/task changes.
