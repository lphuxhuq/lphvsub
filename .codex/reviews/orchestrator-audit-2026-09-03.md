# Orchestrator skill audit — 2026-09-03

## Scope

Audited `codex-orchestrator`, `computer-use-qa`, `antigravity-worker`, all orchestration commands/templates, and persistent `.codex` state against the live Antigravity handshake.

## Findings before changes

- **HIGH:** Prompt provenance was documented but not executable; no deterministic renderer or hash enforcement existed.
- **HIGH:** Agent progress markers had no reconciliation step against task state or `git diff`.
- **MEDIUM:** Resume behavior did not explicitly detect stale handoffs or state conflicts.
- **MEDIUM:** No dedicated command described how to prepare a handoff or synchronize Agent captures.

## Implemented improvements

- Added deterministic `.agents/skills/codex-orchestrator/scripts/render_handoff.py`.
- Added `prepare-handoff.md` and `sync.md` commands.
- Renderer requires `STATUS: READY`, embeds plan/task source metadata, and writes a SHA-256 prompt digest.
- Added visible-marker and acknowledgement gates to Computer Use handoff.
- Added `STATE_CONFLICT`, stale-state, raw-capture, and explicit-marker reconciliation rules.
- Added `templates/handoff.md` provenance fields.

## Verification

- All three skills pass `quick_validate.py`.
- Renderer gate test correctly rejects `TASK-001` when its status is `DONE`.
- Live Computer Use handshake previously verified prompt input, transmission, and progress text recognition.

## Residual risk

The renderer is a local helper and does not itself send UI input; Computer Use must still perform transmission and capture acknowledgement. Product task implementation remains subject to normal automated verification and review.

## Decision

PASS — improvements are in scope and increase determinism without changing product code.
