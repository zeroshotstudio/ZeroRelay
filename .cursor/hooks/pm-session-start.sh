#!/usr/bin/env bash
# Injects PM context at session start (project-relative).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATUS="$ROOT/.cursor/day-plan/STATUS.json"

if [ ! -f "$STATUS" ]; then
  exit 0
fi

python3 <<PY
import json
from pathlib import Path
p = Path("$STATUS")
if not p.exists():
    raise SystemExit(0)
d = json.loads(p.read_text())
if not d.get("pmModeActive"):
    raise SystemExit(0)
cur = d.get("currentTask", "?")
phase = d.get("phase", "?")
done = len(d.get("completed", []))
paused = d.get("userPaused", False)
msg = (
    f"[PM AGENT ACTIVE] Phase: {phase}. Current: {cur}. Done: {done}. "
    f"Paused: {paused}. Read .cursor/day-plan/STATUS.json + SCHEDULE.md. "
    f"You are the PM — lead the workday, one task at a time, update STATUS after each task."
)
print(json.dumps({"continue": True, "additional_context": msg}))
PY
