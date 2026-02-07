#!/bin/bash
# UserPromptSubmit hook: Detect session type from user prompts
# Sets session_type in session_state.json based on keywords

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null)

if [ -z "$PROMPT" ]; then
  exit 0
fi

STATE_DIR="$(dirname "$0")/.."
SESSION_STATE="$STATE_DIR/session_state.json"

# Initialize state file if missing
if [ ! -f "$SESSION_STATE" ]; then
  echo '{"session_type": null, "plan_approved": false}' > "$SESSION_STATE"
fi

# Read current state
if command -v jq >/dev/null 2>&1; then
  CURRENT_TYPE=$(jq -r '.session_type // empty' "$SESSION_STATE" 2>/dev/null)
else
  CURRENT_TYPE=$(grep -o '"session_type"[[:space:]]*:[[:space:]]*"[^"]*"' "$SESSION_STATE" | grep -o '"[^"]*"$' | tr -d '"')
fi

NEW_TYPE=""
MESSAGE=""

# Detect /cc-ready → execution session (default)
if echo "$PROMPT" | grep -qi '/cc-ready'; then
  NEW_TYPE="execution"
  MESSAGE="Execution session started. Plan approval required before TaskCreate."
fi

# Detect explicit session type keywords
if echo "$PROMPT" | grep -qi 'execution session'; then
  NEW_TYPE="execution"
  MESSAGE="Execution session started. Plan approval required before TaskCreate."
elif echo "$PROMPT" | grep -qi 'decision session'; then
  NEW_TYPE="decision"
  MESSAGE="Decision session started. Plan approval required before TaskCreate."
elif echo "$PROMPT" | grep -qi 'exploration session'; then
  NEW_TYPE="exploration"
  MESSAGE="Exploration session started. TaskCreate is unrestricted."
elif echo "$PROMPT" | grep -qi 'review session'; then
  NEW_TYPE="review"
  MESSAGE="Review session started. TaskCreate is unrestricted."
fi

# Update state if session type changed
if [ -n "$NEW_TYPE" ] && [ "$NEW_TYPE" != "$CURRENT_TYPE" ]; then
  if command -v jq >/dev/null 2>&1; then
    PLAN_APPROVED=$(jq -r '.plan_approved // false' "$SESSION_STATE" 2>/dev/null)
    jq --arg st "$NEW_TYPE" '.session_type = $st | .plan_approved = false' "$SESSION_STATE" > "${SESSION_STATE}.tmp" && mv "${SESSION_STATE}.tmp" "$SESSION_STATE"
  else
    # Preserve plan_approved=false on session type change
    echo "{\"session_type\": \"$NEW_TYPE\", \"plan_approved\": false}" > "$SESSION_STATE"
  fi

  echo "{\"systemMessage\": \"$MESSAGE\"}"
fi

exit 0
