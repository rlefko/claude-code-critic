#!/bin/bash
# Pre-tool guard hook for Claude Code Memory
# Validates tool operations before execution
#
# Input: JSON via stdin with tool_name, tool_input
# Exit codes:
#   0 = Allow (proceed with tool execution)
#   2 = Block (stderr message shown to Claude as error)

# Read JSON input from stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

case "$TOOL_NAME" in
    Bash)
        COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

        # Block dangerous git operations
        if echo "$COMMAND" | grep -qE 'git\s+(push\s+.*--force|reset\s+--hard|clean\s+-fd)'; then
            echo "Blocked: Dangerous git operation detected. Use with caution." >&2
            exit 2
        fi

        # Warn about rm -rf on important directories
        if echo "$COMMAND" | grep -qE 'rm\s+-rf\s+(/|~|\.\./)'; then
            echo "Blocked: Potentially destructive rm -rf command." >&2
            exit 2
        fi
        ;;

    Write|Edit)
        FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

        # Block writes to sensitive files
        case "$FILE_PATH" in
            */.env|*/credentials*|*/secrets*|*/.ssh/*|*/id_rsa*)
                echo "Blocked: Cannot modify sensitive file: $FILE_PATH" >&2
                exit 2
                ;;
        esac
        ;;
esac

# Allow by default
exit 0
