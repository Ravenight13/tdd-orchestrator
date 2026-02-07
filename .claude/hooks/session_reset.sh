#!/bin/bash
# SessionStart hook: Reset session state files for a clean session
# Runs on every new session to ensure no stale state carries over

STATE_DIR="$(dirname "$0")/.."
SESSION_STATE="$STATE_DIR/session_state.json"
TASK_STATE="$STATE_DIR/task_progress_state.json"

# Reset session state
if command -v jq >/dev/null 2>&1; then
  echo '{"session_type": null, "plan_approved": false}' | jq '.' > "$SESSION_STATE"
  echo '{"in_progress_task": null}' | jq '.' > "$TASK_STATE"
else
  echo '{"session_type": null, "plan_approved": false}' > "$SESSION_STATE"
  echo '{"in_progress_task": null}' > "$TASK_STATE"
fi

exit 0
