# Codex → Antigravity Orchestrator

This repository uses Codex as the orchestration authority and Antigravity as the implementation worker.

## Operating rules

- Inspect the repository, `git status`, branch, entry points, dependencies, tests, and existing instructions before editing.
- Analyze and plan before implementation. Break substantial work into atomic, dependency-aware tasks with acceptance criteria.
- Delegate implementation tasks to Antigravity through Computer Use when both are actually available. A report or assumption is not evidence of delegation.
- Keep Codex responsible for architecture, scope, root-cause analysis, verification, review, state, and PASS/FAIL decisions.
- Keep Antigravity responsible for the explicitly assigned source changes, local commands, tests, and implementation report; it must not redefine architecture or scope.
- Use Computer Use for applicable GUI/UI/UX verification, while still running code-level tests. Never claim UI verification without interaction evidence.
- Review every completed task and inspect the actual diff against the worker report. Do not mark `DONE` without appropriate evidence.
- Persist state and evidence under `.codex/` so another session can resume without relying on chat history.
- Do not silently expand scope, overwrite unrelated user changes, remove functionality, expose secrets, or use destructive Git operations without explicit authorization.
- If Computer Use cannot be used, record `COMPUTER_USE_UNAVAILABLE`, continue only with non-UI verification, and do not claim Antigravity control or UI/UX verification.
- If Antigravity is unreachable, wait/request it or obtain explicit authorization for a separately labelled Codex-owned implementation; never relabel Codex work as Antigravity work.
- Generate implementation prompts from an approved plan plus a `READY` task using the deterministic handoff renderer; do not send ad-hoc prompts.
- Reconcile Agent progress markers with task state and `git diff`; stop on `STATE_CONFLICT` or stale handoff evidence.

## Workflow entrypoint

Load `.agents/skills/codex-orchestrator/SKILL.md` for the lifecycle and command mapping. Existing project conventions in `.agents/AGENT-WORKFLOW.md`, `.agents/rules/`, and `.agents/workflows/` remain in force; this orchestrator adds Antigravity handoff, Computer Use evidence, and resumable state.
