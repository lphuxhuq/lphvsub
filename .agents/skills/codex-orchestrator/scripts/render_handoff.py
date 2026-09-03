#!/usr/bin/env python3
"""Render a provenance-bound Antigravity handoff from an approved plan and READY task."""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import re


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def field(text: str, name: str) -> str:
    match = re.search(rf"(?mi)^\s*{re.escape(name)}\s*:\s*(.*?)\s*$", text)
    return match.group(1).strip() if match else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = read(args.plan)
    task = read(args.task)
    heading = re.search(r"(?mi)^#\s*((?:TASK|FIX)-\d+)", task)
    task_id = field(task, "TASK ID") or (heading.group(1) if heading else "")
    status = field(task, "STATUS")
    if not task_id:
        raise SystemExit("ERROR: task file has no TASK-### or FIX-### identifier")
    if status.upper() != "READY":
        raise SystemExit(f"ERROR: {task_id} must be STATUS: READY (found {status or 'missing'})")
    if not plan.strip():
        raise SystemExit("ERROR: plan is empty")

    generated = datetime.now(timezone.utc).isoformat()
    body = f"""# Codex-generated Antigravity handoff — {task_id}

SOURCE PLAN: {args.plan.as_posix()}
SOURCE TASK: {args.task.as_posix()}
GENERATED AT: {generated}
TASK STATUS AT GENERATION: {status}

## Task source

{task}

## Approved plan context

{plan}

## Computer Use transmission contract

- Type this rendered document verbatim into the Antigravity Agent composer.
- Confirm the visible marker `{task_id}` before sending.
- After sending, capture acknowledgement/progress and match the same task ID.
- Antigravity must not expand scope or modify orchestration state.
"""
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    output = body + f"\nPROMPT SHA256: {digest}\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8", newline="\n")
    print(f"Rendered {task_id} -> {args.output} (sha256={digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
