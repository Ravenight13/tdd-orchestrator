#!/bin/bash
# PreToolUse hook (TaskCreate): Block TaskCreate until plan is approved
# HARD BLOCK (exit 2) when session_type is execution/decision AND plan_approved is false
# Exploration/review sessions and no-session-type are exempt

STATE_DIR="$(dirname "$0")/.."
SESSION_STATE="$STATE_DIR/session_state.json"

# No state file → no enforcement
if [ ! -f "$SESSION_STATE" ]; then
  exit 0
fi

# Read session state
if command -v jq >/dev/null 2>&1; then
  SESSION_TYPE=$(jq -r '.session_type // empty' "$SESSION_STATE" 2>/dev/null)
  PLAN_APPROVED=$(jq -r '.plan_approved // false' "$SESSION_STATE" 2>/dev/null)
else
  SESSION_TYPE=$(grep -o '"session_type"[[:space:]]*:[[:space:]]*"[^"]*"' "$SESSION_STATE" | grep -o '"[^"]*"$' | tr -d '"')
  PLAN_APPROVED=$(grep -o '"plan_approved"[[:space:]]*:[[:space:]]*[a-z]*' "$SESSION_STATE" | grep -o '[a-z]*$')
fi

# No session type set → exempt
if [ -z "$SESSION_TYPE" ] || [ "$SESSION_TYPE" = "null" ]; then
  exit 0
fi

# Exploration and review sessions → exempt
if [ "$SESSION_TYPE" = "exploration" ] || [ "$SESSION_TYPE" = "review" ]; then
  exit 0
fi

# Execution and decision sessions require plan approval
if [ "$SESSION_TYPE" = "execution" ] || [ "$SESSION_TYPE" = "decision" ]; then
  if [ "$PLAN_APPROVED" != "true" ]; then
    echo '{"error": "BLOCKED: TaskCreate requires plan approval first. Use EnterPlanMode → plan → ExitPlanMode before creating tasks. (task-execution.md: Step 2)"}' >&2
    exit 2
  fi
fi

exit 0
