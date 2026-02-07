#!/bin/bash
# Stop hook: Warn about in-progress tasks when session ends
# Soft warning only (systemMessage, not a hard block)

STATE_DIR="$(dirname "$0")/.."
TASK_STATE="$STATE_DIR/task_progress_state.json"

# No state file → nothing to warn about
if [ ! -f "$TASK_STATE" ]; then
  echo '{"systemMessage": "Session ending. Consider running /cc-handoff to document this session."}'
  exit 0
fi

# Read current in_progress task
if command -v jq >/dev/null 2>&1; then
  CURRENT_TASK=$(jq -r '.in_progress_task // empty' "$TASK_STATE" 2>/dev/null)
else
  CURRENT_TASK=$(grep -o '"in_progress_task"[[:space:]]*:[[:space:]]*"[^"]*"' "$TASK_STATE" | grep -o '"[^"]*"$' | tr -d '"')
fi

if [ -n "$CURRENT_TASK" ] && [ "$CURRENT_TASK" != "null" ]; then
  echo "{\"systemMessage\": \"Warning: Task #$CURRENT_TASK is still in_progress. Consider completing or documenting it before ending the session. Run /cc-handoff to capture session state.\"}"
else
  echo '{"systemMessage": "Session ending. Consider running /cc-handoff to document this session."}'
fi

exit 0
