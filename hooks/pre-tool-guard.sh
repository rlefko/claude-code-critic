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
        # Fixed: Use proper quote escaping and include := for various languages
        if echo "$CONTENT" | grep -qiE "(password|api_key|secret|token|private_key)\s*[:=]\s*[\"'][^\"']+[\"']"; then
            add_warning "[SECURITY] Potential hardcoded secret detected. Use environment variables instead."
        fi

        # Check for SQL injection patterns (string concatenation in queries)
        # Fixed: Multiple patterns for different injection vectors
        SQL_INJECTION_FOUND=0
        # Python f-strings with double or single quotes
        if echo "$CONTENT" | grep -qE 'f["'"'"'](SELECT|INSERT|UPDATE|DELETE)[^"'"'"']*\{'; then
            SQL_INJECTION_FOUND=1
        fi
        # JavaScript template literals
        if echo "$CONTENT" | grep -qE '`(SELECT|INSERT|UPDATE|DELETE).*\$\{'; then
            SQL_INJECTION_FOUND=1
        fi
        # String concatenation
        if echo "$CONTENT" | grep -qE '"(SELECT|INSERT|UPDATE|DELETE)[^"]*"\s*\+'; then
            SQL_INJECTION_FOUND=1
        fi
        # Python .format()
        if echo "$CONTENT" | grep -qE '\.(format|substitute)\s*\(.*\).*(SELECT|INSERT|UPDATE|DELETE)|(SELECT|INSERT|UPDATE|DELETE).*\.(format|substitute)\s*\('; then
            SQL_INJECTION_FOUND=1
        fi
        if [ "$SQL_INJECTION_FOUND" -eq 1 ]; then
            add_warning "[SECURITY] Potential SQL injection: avoid string interpolation in queries. Use parameterized queries."
        fi

        # Check for XSS patterns (this one works correctly)
        if echo "$CONTENT" | grep -qE '(innerHTML|dangerouslySetInnerHTML|v-html)'; then
            add_warning "[SECURITY] innerHTML/dangerouslySetInnerHTML detected. Ensure input is sanitized."
        fi

        # === QUALITY CHECKS ===

        # Check for TODO without ticket reference
        # Fixed: Check each TODO line individually, not entire file
        while IFS= read -r line; do
            if [ -n "$line" ]; then
                if ! echo "$line" | grep -qE '[A-Z]+-[0-9]+'; then
                    # Truncate long lines for display
                    truncated="${line:0:60}"
                    add_warning "[QUALITY] TODO without ticket: $truncated"
                    break  # Only warn once per edit
                fi
            fi
        done < <(echo "$CONTENT" | grep -E '#\s*TODO|//\s*TODO')

        # Check for linter disables without explanation
        # Fixed: Check each suppression line individually
        # Accept as explained if: has code (E501), brackets ([attr]), colon+code, or trailing comment
        while IFS= read -r line; do
            if [ -n "$line" ]; then
                # Consider it explained if there's meaningful content after keyword:
                # - Colon followed by code: "noqa: E501"
                # - Brackets: "type: ignore[attr-defined]"
                # - Trailing comment: "noqa  # reason"
                # - Or any content >= 3 chars after keyword
                if ! echo "$line" | grep -qE '(noqa|type:\s*ignore|@ts-ignore|eslint-disable|pylint:\s*disable)(\s*[:\[].+|.{3,})'; then
                    truncated="${line:0:60}"
                    add_warning "[QUALITY] Unexplained suppression: $truncated"
                    break  # Only warn once per edit
                fi
            fi
        done < <(echo "$CONTENT" | grep -E '# noqa|# type: ignore|// @ts-ignore|// eslint-disable|# pylint: disable')

        # === RESILIENCE CHECKS ===

        # Check for swallowed exceptions
        # Fixed: Handle multiline by collapsing to single line for pattern matching
        COLLAPSED=$(echo "$CONTENT" | tr '\n' ' ')
        if echo "$COLLAPSED" | grep -qE 'except[^:]*:\s*pass|catch\s*\([^)]*\)\s*\{\s*\}'; then
            add_warning "[RESILIENCE] Swallowed exception detected. Log errors or handle specifically."
        fi

        # Check for missing timeout in HTTP calls
        # Fixed: Check each request line individually
        while IFS= read -r line; do
            if [ -n "$line" ]; then
                if ! echo "$line" | grep -qE 'timeout\s*='; then
                    truncated="${line:0:50}"
                    add_warning "[RESILIENCE] HTTP call may need timeout: $truncated"
                    break  # Only warn once per edit
                fi
            fi
        done < <(echo "$CONTENT" | grep -E 'requests\.(get|post|put|delete|patch)\(')

        # === DOCUMENTATION CHECKS ===
        # Note: These checks have a fundamental limitation - they can only detect if
        # ANY docstring/JSDoc exists in the content, not whether each function has one.
        # This is a bash limitation; proper per-function detection requires AST parsing.
        # Messages are advisory rather than diagnostic.

        # Check for public function without docstring (Python)
        if echo "$FILE_PATH" | grep -qE '\.py$'; then
            if echo "$CONTENT" | grep -qE '^def [a-z]'; then
                # Check for triple quotes (either """ or ''')
                if ! echo "$CONTENT" | grep -qE '("""|'"'"''"'"''"'"')'; then
                    add_warning "[DOCS] Python function added - ensure it has a docstring if public."
                fi
            fi
        fi

        # Check for public function without JSDoc (JavaScript/TypeScript)
        if echo "$FILE_PATH" | grep -qE '\.(js|ts|jsx|tsx)$'; then
            if echo "$CONTENT" | grep -qE '^export\s+(async\s+)?(function|const|default)'; then
                if ! echo "$CONTENT" | grep -qE '/\*\*'; then
                    add_warning "[DOCS] Exported function added - ensure it has JSDoc if public API."
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
