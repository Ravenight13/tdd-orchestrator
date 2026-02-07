#!/bin/bash
# PreToolUse hook (TaskUpdate): Block multiple tasks in_progress simultaneously
# HARD BLOCK (exit 2) when setting a different task to in_progress while one is already active
# Same task ID re-set is allowed (idempotent)

INPUT=$(cat)

# Extract the status being set
STATUS=$(echo "$INPUT" | jq -r '.tool_input.status // empty' 2>/dev/null)

# Only gate in_progress transitions
if [ "$STATUS" != "in_progress" ]; then
  exit 0
fi

# Extract task ID being updated
TASK_ID=$(echo "$INPUT" | jq -r '.tool_input.taskId // empty' 2>/dev/null)

STATE_DIR="$(dirname "$0")/.."
TASK_STATE="$STATE_DIR/task_progress_state.json"

# No state file → no enforcement
if [ ! -f "$TASK_STATE" ]; then
  exit 0
fi

# Read current in_progress task
if command -v jq >/dev/null 2>&1; then
  CURRENT_TASK=$(jq -r '.in_progress_task // empty' "$TASK_STATE" 2>/dev/null)
else
  CURRENT_TASK=$(grep -o '"in_progress_task"[[:space:]]*:[[:space:]]*"[^"]*"' "$TASK_STATE" | grep -o '"[^"]*"$' | tr -d '"')
fi

# No task in progress → allow
if [ -z "$CURRENT_TASK" ] || [ "$CURRENT_TASK" = "null" ]; then
  exit 0
fi

# Same task → allow (idempotent)
if [ "$TASK_ID" = "$CURRENT_TASK" ]; then
  exit 0
fi

# Different task already in progress → block
echo "{\"error\": \"BLOCKED: Task #$CURRENT_TASK is already in_progress. Complete or delete it before starting task #$TASK_ID. (task-execution.md: one task at a time)\"}" >&2
exit 2
