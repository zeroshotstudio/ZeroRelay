#!/usr/bin/env bash
# Updates tracker on agent stop; emits followup_message to keep PM chain alive.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATUS="$ROOT/.cursor/day-plan/STATUS.json"

if [ ! -f "$STATUS" ]; then
  echo '{}'
  exit 0
fi

python3 <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

status_path = Path(".cursor/day-plan/STATUS.json")
if not status_path.exists():
    print("{}")
    raise SystemExit(0)

d = json.loads(status_path.read_text())
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
d["lastAgentStopAt"] = now

active = d.get("pmModeActive", False)
paused = d.get("userPaused", False)
auto = d.get("autoFollowup", True)
current = d.get("currentTask")
completed_ids = {c.get("id") for c in d.get("completed", [])}

status_path.write_text(json.dumps(d, indent=2) + "\n")

# Follow up only when PM mode is on, not paused, auto enabled, and current task not completed
if active and auto and not paused and current and current not in completed_ids:
    msg = (
        "PM CONTINUE (auto): Read .cursor/day-plan/STATUS.json. You are the PM. "
        f"Resume task {current} immediately if work is incomplete. "
        "One task at a time. Update STATUS + todos when done. "
        "If blocked on user action, post a one-line nudge and pivot to next unblocked task."
    )
    print(json.dumps({"followup_message": msg}))
else:
    print("{}")
PY
