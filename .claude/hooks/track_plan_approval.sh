#!/bin/bash
# PostToolUse hook (ExitPlanMode): Mark plan as approved in session state
# Unlocks TaskCreate for execution/decision sessions

STATE_DIR="$(dirname "$0")/.."
SESSION_STATE="$STATE_DIR/session_state.json"

# Initialize state file if missing
if [ ! -f "$SESSION_STATE" ]; then
  echo '{"session_type": null, "plan_approved": false}' > "$SESSION_STATE"
fi

# Set plan_approved=true
if command -v jq >/dev/null 2>&1; then
  jq '.plan_approved = true' "$SESSION_STATE" > "${SESSION_STATE}.tmp" && mv "${SESSION_STATE}.tmp" "$SESSION_STATE"
else
  # Read current session_type and rebuild
  SESSION_TYPE=$(grep -o '"session_type"[[:space:]]*:[[:space:]]*"[^"]*"' "$SESSION_STATE" | grep -o '"[^"]*"$' | tr -d '"')
  if [ -n "$SESSION_TYPE" ] && [ "$SESSION_TYPE" != "null" ]; then
    echo "{\"session_type\": \"$SESSION_TYPE\", \"plan_approved\": true}" > "$SESSION_STATE"
  else
    echo '{"session_type": null, "plan_approved": true}' > "$SESSION_STATE"
  fi
fi

echo '{"systemMessage": "Plan approved. TaskCreate unlocked."}'

exit 0
