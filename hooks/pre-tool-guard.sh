#!/bin/bash
# Pre-tool guard hook for Claude Code Memory
# Validates tool operations before execution
#
# Enforces tech debt standards from the diagnosis suite:
# - Security: /resecure patterns
# - Quality: /refactor, /retest patterns
# - Documentation: /redocument patterns
#
# Input: JSON via stdin with tool_name, tool_input
# Exit codes:
#   0 = Allow (proceed with tool execution)
#   1 = Warn (non-blocking, shown to user)
#   2 = Block (stderr message shown to Claude as error)

# Read JSON input from stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
WARNINGS=""

# Helper function to add warnings
add_warning() {
    if [ -z "$WARNINGS" ]; then
        WARNINGS="$1"
    else
        WARNINGS="$WARNINGS\n$1"
    fi
}

case "$TOOL_NAME" in
    Bash)
        COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

        # === SECURITY CHECKS ===

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

        # Block commits that might contain secrets
        if echo "$COMMAND" | grep -qE 'git\s+(commit|add)'; then
            # Check if commit message or staged files contain secret patterns
            add_warning "[SECURITY] Verify no secrets in staged files before commit"
        fi
        ;;

    Write|Edit)
        FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
        CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty')

        # === SECURITY CHECKS ===

        # Block writes to sensitive files
        case "$FILE_PATH" in
            */.env|*/credentials*|*/secrets*|*/.ssh/*|*/id_rsa*)
                echo "Blocked: Cannot modify sensitive file: $FILE_PATH" >&2
                exit 2
                ;;
        esac

        # Check for hardcoded secrets patterns
        if echo "$CONTENT" | grep -qiE '(password|api_key|secret|token|private_key)\s*=\s*["\x27][^"\x27]+["\x27]'; then
            add_warning "[SECURITY] Potential hardcoded secret detected. Use environment variables instead."
        fi

        # Check for SQL injection patterns (string concatenation in queries)
        if echo "$CONTENT" | grep -qE 'f["\x27](SELECT|INSERT|UPDATE|DELETE|FROM|WHERE).*\{'; then
            add_warning "[SECURITY] Potential SQL injection: avoid f-strings in queries. Use parameterized queries."
        fi

        # Check for XSS patterns
        if echo "$CONTENT" | grep -qE '(innerHTML|dangerouslySetInnerHTML|v-html)'; then
            add_warning "[SECURITY] innerHTML/dangerouslySetInnerHTML detected. Ensure input is sanitized."
        fi

        # === QUALITY CHECKS ===

        # Check for TODO without ticket reference
        if echo "$CONTENT" | grep -qE '#\s*TODO[^:]*$|//\s*TODO[^:]*$'; then
            if ! echo "$CONTENT" | grep -qE 'TODO.*[A-Z]+-[0-9]+'; then
                add_warning "[QUALITY] TODO without ticket reference. Consider adding ticket ID (e.g., TODO: PROJ-123)"
            fi
        fi

        # Check for linter disables without explanation
        if echo "$CONTENT" | grep -qE '(# noqa|# type: ignore|// @ts-ignore|// eslint-disable|# pylint: disable)'; then
            if ! echo "$CONTENT" | grep -qE '(noqa|type: ignore|@ts-ignore|eslint-disable|pylint: disable).*#|.*//.*because|.*#.*reason'; then
                add_warning "[QUALITY] Linter suppression without explanation. Add comment explaining why."
            fi
        fi

        # === RESILIENCE CHECKS ===

        # Check for swallowed exceptions
        if echo "$CONTENT" | grep -qE 'except.*:\s*pass|catch.*\{\s*\}'; then
            add_warning "[RESILIENCE] Swallowed exception detected. Log errors or handle specifically."
        fi

        # Check for missing timeout in HTTP calls
        if echo "$CONTENT" | grep -qE 'requests\.(get|post|put|delete|patch)\([^)]*\)'; then
            if ! echo "$CONTENT" | grep -qE 'timeout\s*='; then
                add_warning "[RESILIENCE] HTTP call without timeout. Add timeout parameter."
            fi
        fi

        # === DOCUMENTATION CHECKS ===

        # Check for public function without docstring (Python)
        if echo "$FILE_PATH" | grep -qE '\.py$'; then
            if echo "$CONTENT" | grep -qE '^def [a-z][a-z_0-9]*\('; then
                if ! echo "$CONTENT" | grep -qE '^\s*("""|\x27\x27\x27)'; then
                    add_warning "[DOCS] Public function may need docstring. Consider adding documentation."
                fi
            fi
        fi

        # Check for public function without JSDoc (JavaScript/TypeScript)
        if echo "$FILE_PATH" | grep -qE '\.(js|ts|jsx|tsx)$'; then
            if echo "$CONTENT" | grep -qE '^export\s+(async\s+)?function'; then
                if ! echo "$CONTENT" | grep -qE '/\*\*'; then
                    add_warning "[DOCS] Exported function may need JSDoc. Consider adding documentation."
                fi
            fi
        fi
        ;;
esac

# Output warnings (non-blocking)
if [ -n "$WARNINGS" ]; then
    echo -e "$WARNINGS" >&2
    exit 1  # Non-blocking warning
fi

# Allow by default
exit 0
