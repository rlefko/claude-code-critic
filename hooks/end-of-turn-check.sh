#!/bin/bash
# End-of-turn check hook for Claude Code Memory
# Triggered at end of each Claude turn (Stop hook)
#
# Runs comprehensive quality checks on all uncommitted changes.
# Unlike PostToolUse (<300ms, single file), this can BLOCK Claude
# if critical issues are found (exit code 2).
#
# Input: JSON via stdin with session context
# Exit codes:
#   0 = Success (no critical issues)
#   1 = Non-blocking warnings (shown to user)
#   2 = Critical issues - BLOCKS Claude (triggers self-repair)
#
# Performance budget: <5000ms total

set -e

# Cross-platform stdin read with timeout (prevents hang in background mode)
read_stdin_with_timeout() {
    local timeout_secs="${1:-10}"
    if command -v timeout &> /dev/null; then
        timeout "$timeout_secs" cat 2>/dev/null || true
    elif command -v gtimeout &> /dev/null; then
        gtimeout "$timeout_secs" cat 2>/dev/null || true
    else
        # Fallback: use read with built-in timeout (line by line)
        local input=""
        while IFS= read -r -t "$timeout_secs" line; do
            input+="$line"$'\n'
        done
        printf '%s' "$input"
    fi
}

# Read JSON input from stdin with timeout (may be empty for Stop hook)
INPUT=$(read_stdin_with_timeout 5) || true

# Find project root by looking for .git or .mcp.json
find_project_root() {
    local dir="$1"
    while [ "$dir" != "/" ]; do
        if [ -d "$dir/.git" ] || [ -f "$dir/.mcp.json" ]; then
            echo "$dir"
            return 0
        fi
        dir=$(dirname "$dir")
    done
    return 1
}

# Get project root from current directory
PROJECT_DIR=$(find_project_root "$(pwd)")
if [ -z "$PROJECT_DIR" ]; then
    # Fallback to current directory
    PROJECT_DIR=$(pwd)
fi

# Check if claude-indexer is available
if ! command -v claude-indexer &> /dev/null; then
    # Not installed globally, skip silently
    exit 0
fi

# ============================================================
# Run Comprehensive Stop Checks (<5000ms budget)
# ============================================================

RESULT_OUTPUT=""
RESULT_EXIT_CODE=0

# Run comprehensive quality checks with JSON output
RESULT_OUTPUT=$(claude-indexer stop-check -p "$PROJECT_DIR" --json 2>/dev/null) || RESULT_EXIT_CODE=$?

# ============================================================
# Handle Results Based on Exit Code
# ============================================================

case $RESULT_EXIT_CODE in
    0)
        # Clean - no issues
        exit 0
        ;;
    1)
        # Non-blocking warnings - show to user
        if [ -n "$RESULT_OUTPUT" ]; then
            # Extract status and findings count
            STATUS=$(echo "$RESULT_OUTPUT" | jq -r '.status // "ok"' 2>/dev/null)
            TOTAL=$(echo "$RESULT_OUTPUT" | jq -r '.summary.total // 0' 2>/dev/null)

            if [ "$STATUS" != "ok" ] && [ "$TOTAL" -gt 0 ]; then
                echo ""
                echo "=== Quality Check Warnings ==="
                echo ""

                # Format findings for display
                echo "$RESULT_OUTPUT" | jq -r '.findings[] | "[\(.severity | ascii_upcase)] \(.rule_id)\n   \(.file_path):\(.line_number // "?")\n   \(.summary)\n"' 2>/dev/null

                # Show summary
                CRITICAL=$(echo "$RESULT_OUTPUT" | jq -r '.summary.critical // 0' 2>/dev/null)
                HIGH=$(echo "$RESULT_OUTPUT" | jq -r '.summary.high // 0' 2>/dev/null)
                MEDIUM=$(echo "$RESULT_OUTPUT" | jq -r '.summary.medium // 0' 2>/dev/null)
                FILES=$(echo "$RESULT_OUTPUT" | jq -r '.files_checked // 0' 2>/dev/null)
                TIME=$(echo "$RESULT_OUTPUT" | jq -r '.execution_time_ms // 0' 2>/dev/null)

                echo "---"
                echo "Found $TOTAL issue(s): $CRITICAL critical, $HIGH high, $MEDIUM medium"
                echo "Checked $FILES files in ${TIME}ms"
                echo ""
            fi
        fi
        exit 1
        ;;
    2)
        # CRITICAL - Block Claude and format for self-repair
        if [ -n "$RESULT_OUTPUT" ]; then
            echo ""
            echo "=== QUALITY CHECK BLOCKED ==="
            echo ""

            # Format each finding for Claude's self-repair
            echo "$RESULT_OUTPUT" | jq -r '
                .findings[] |
                "\(.severity | ascii_upcase): \(.rule_id) - \(.file_path):\(.line_number // "?")\nDescription: \(.summary)\nSuggestion: \(.remediation_hints[0] // "Review and fix the issue")\n---"
            ' 2>/dev/null

            # Show summary
            CRITICAL=$(echo "$RESULT_OUTPUT" | jq -r '.summary.critical // 0' 2>/dev/null)
            HIGH=$(echo "$RESULT_OUTPUT" | jq -r '.summary.high // 0' 2>/dev/null)
            TOTAL=$(echo "$RESULT_OUTPUT" | jq -r '.summary.total // 0' 2>/dev/null)
            FILES=$(echo "$RESULT_OUTPUT" | jq -r '.files_checked // 0' 2>/dev/null)
            TIME=$(echo "$RESULT_OUTPUT" | jq -r '.execution_time_ms // 0' 2>/dev/null)

            echo ""
            echo "Found $TOTAL blocking issue(s): $CRITICAL critical, $HIGH high"
            echo "Checked $FILES files in ${TIME}ms"
            echo ""
            echo "Please fix these issues to proceed."
            echo ""
        fi
        exit 2
        ;;
    *)
        # Unknown error - don't block
        exit 0
        ;;
esac
