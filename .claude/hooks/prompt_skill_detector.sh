#!/bin/bash
# UserPromptSubmit hook: Suggest relevant slash commands based on prompt keywords
# Outputs soft systemMessage hints (never blocks)

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null)

if [ -z "$PROMPT" ]; then
  exit 0
fi

# Convert to lowercase for matching
PROMPT_LOWER=$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]')

SUGGESTIONS=""

# Check for handoff-related keywords (but not if already using the command)
if echo "$PROMPT_LOWER" | grep -q 'handoff' && ! echo "$PROMPT_LOWER" | grep -q '/cc-handoff'; then
  SUGGESTIONS="Consider using /cc-handoff for session handoff documentation."
fi

# Check for commit-related keywords
if echo "$PROMPT_LOWER" | grep -q 'commit' && ! echo "$PROMPT_LOWER" | grep -q '/commit'; then
  if [ -n "$SUGGESTIONS" ]; then
    SUGGESTIONS="$SUGGESTIONS "
  fi
  SUGGESTIONS="${SUGGESTIONS}Consider using /commit for structured git commits."
fi

# Check for review-related keywords
if echo "$PROMPT_LOWER" | grep -q 'review' && ! echo "$PROMPT_LOWER" | grep -q '/code-review'; then
  if [ -n "$SUGGESTIONS" ]; then
    SUGGESTIONS="$SUGGESTIONS "
  fi
  SUGGESTIONS="${SUGGESTIONS}Consider using /code-review for structured code review."
fi

# Check for test-related keywords
if echo "$PROMPT_LOWER" | grep -qE '\btest\b|\btests\b' && ! echo "$PROMPT_LOWER" | grep -q '/quick-test'; then
  if [ -n "$SUGGESTIONS" ]; then
    SUGGESTIONS="$SUGGESTIONS "
  fi
  SUGGESTIONS="${SUGGESTIONS}Consider using /quick-test for quick project health checks."
fi

if [ -n "$SUGGESTIONS" ]; then
  # Escape for JSON
  SUGGESTIONS_ESCAPED=$(echo "$SUGGESTIONS" | sed 's/"/\\"/g')
  echo "{\"systemMessage\": \"$SUGGESTIONS_ESCAPED\"}"
fi

exit 0
