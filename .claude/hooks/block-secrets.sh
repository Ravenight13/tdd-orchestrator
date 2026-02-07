#!/bin/bash
# PreToolUse hook: Block access to sensitive files
# Returns exit code 2 to block the tool call with a message

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // empty')

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

if echo "$FILE_PATH" | grep -qEi '\.env($|\.)|(^|/)credentials\.|secrets/|\.ssh/|\.aws/|\.pem$|\.key$'; then
  echo '{"error": "Blocked: Access to sensitive file. Use environment variables instead."}' >&2
  exit 2
fi

exit 0
