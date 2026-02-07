#!/bin/bash
# PostToolUse hook (TaskUpdate): Track which task is in_progress
# On status=in_progress: records task ID
# On status=completed|deleted: clears in_progress_task if matching

INPUT=$(cat)

# Extract status and task ID from tool input
STATUS=$(echo "$INPUT" | jq -r '.tool_input.status // empty' 2>/dev/null)
TASK_ID=$(echo "$INPUT" | jq -r '.tool_input.taskId // empty' 2>/dev/null)

# Only act on relevant status transitions
if [ -z "$STATUS" ] || [ -z "$TASK_ID" ]; then
  exit 0
fi

STATE_DIR="$(dirname "$0")/.."
TASK_STATE="$STATE_DIR/task_progress_state.json"

# Initialize state file if missing
if [ ! -f "$TASK_STATE" ]; then
  echo '{"in_progress_task": null}' > "$TASK_STATE"
fi

case "$STATUS" in
  in_progress)
    if command -v jq >/dev/null 2>&1; then
      jq --arg tid "$TASK_ID" '.in_progress_task = $tid' "$TASK_STATE" > "${TASK_STATE}.tmp" && mv "${TASK_STATE}.tmp" "$TASK_STATE"
    else
      echo "{\"in_progress_task\": \"$TASK_ID\"}" > "$TASK_STATE"
    fi
    ;;
  completed|deleted)
    # Only clear if the completed/deleted task matches the in_progress one
    if command -v jq >/dev/null 2>&1; then
      CURRENT_TASK=$(jq -r '.in_progress_task // empty' "$TASK_STATE" 2>/dev/null)
    else
      CURRENT_TASK=$(grep -o '"in_progress_task"[[:space:]]*:[[:space:]]*"[^"]*"' "$TASK_STATE" | grep -o '"[^"]*"$' | tr -d '"')
    fi

    if [ "$TASK_ID" = "$CURRENT_TASK" ]; then
      if command -v jq >/dev/null 2>&1; then
        jq '.in_progress_task = null' "$TASK_STATE" > "${TASK_STATE}.tmp" && mv "${TASK_STATE}.tmp" "$TASK_STATE"
      else
        echo '{"in_progress_task": null}' > "$TASK_STATE"
      fi
    fi
    ;;
esac

exit 0
