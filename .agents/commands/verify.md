# Verify

Run the smallest relevant syntax/type/unit/integration/build/runtime checks first, then regression checks. Validate the Antigravity report against the diff. For GUI work, run `.agents/skills/computer-use-qa/SKILL.md` and record actual UI evidence; if unavailable record `COMPUTER_USE_UNAVAILABLE`, never a false PASS. Save commands, outputs, timestamps, and evidence paths in `.codex/state/test-results.md` and `.codex/evidence/`. A failed check creates a root-cause-driven FIX task.
