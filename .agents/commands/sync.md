# Sync Agent progress

After each fresh Agent-panel capture, preserve the raw text/screenshot in `.codex/evidence/agent-<TASK-ID>-<timestamp>.*`. Extract only explicit markers (`TASK ID`, `STATUS`, `PROGRESS`, `FILES CHANGED`, `TEST RESULTS`, `BLOCKERS`, `NEXT ACTION`) and update `.codex/state/current-task.md` plus `.codex/state/progress.md`. Compare reported files/status with `git diff` and the task file. Mark `STATE_CONFLICT` when they disagree; Codex must resolve the conflict before advancing. Worker suggestions never change task state automatically.
