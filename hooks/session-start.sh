#!/bin/bash
# Session start hook for Claude Code Memory
# Triggered at the start of each Claude session (SessionStart hook)
#
# Performs system health checks and displays welcome message:
# - Verifies Qdrant connectivity
# - Checks index freshness (suggests re-index if stale)
# - Shows git context (branch, uncommitted changes)
# - Displays memory-first workflow reminder
#
# Input: JSON via stdin with session context (cwd)
# Exit codes:
#   0 = All healthy
#   1 = Warnings present (informational, never blocks)
#
# Performance budget: <2000ms total (graceful degradation)

set -e

# Cross-platform stdin read with timeout (prevents hang)
read_stdin_with_timeout() {
    local timeout_secs="${1:-5}"
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

# Read JSON input from stdin with timeout
INPUT=$(read_stdin_with_timeout 5) || true

# Extract cwd from input or use current directory
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
if [ -z "$CWD" ]; then
    CWD=$(pwd)
fi

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

PROJECT_DIR=$(find_project_root "$CWD")
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR="$CWD"
fi

# Get collection name from environment or .mcp.json
COLLECTION="${CLAUDE_MEMORY_COLLECTION:-}"

if [ -z "$COLLECTION" ]; then
    # Try to extract from .mcp.json
    if [ -f "$PROJECT_DIR/.mcp.json" ]; then
        COLLECTION=$(jq -r '.mcpServers | keys[0] | sub("-memory$"; "")' "$PROJECT_DIR/.mcp.json" 2>/dev/null)
    fi
fi

# Fallback: derive from project directory name
if [ -z "$COLLECTION" ] || [ "$COLLECTION" = "null" ]; then
    # Sanitize project directory name: lowercase, replace non-alphanumeric with hyphen
    COLLECTION=$(basename "$PROJECT_DIR" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g')
fi

# Check if claude-indexer is available
if ! command -v claude-indexer &> /dev/null; then
    # claude-indexer not installed, show basic context instead
    echo ""
    echo "=== Session Context ==="
    echo ""
    echo "System Health:"
    echo "  [WARN] claude-indexer not installed"
    echo "         Install: pip install claude-indexer"
    echo ""

    if command -v git &> /dev/null && [ -d "$PROJECT_DIR/.git" ]; then
        echo "Git Context:"
        BRANCH=$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
        echo "  Branch: $BRANCH"

        CHANGES=$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
        if [ "$CHANGES" -gt 0 ]; then
            echo "  Uncommitted: $CHANGES file(s)"
        fi

        echo "  Recent commits:"
        git -C "$PROJECT_DIR" log --oneline -3 --format="    - %s" 2>/dev/null || echo "    (no commits)"
    fi

    echo ""
    exit 0
fi

# ============================================================
# Run Session Start Check (<2000ms budget)
# ============================================================

# Run session start check with graceful error handling
claude-indexer session-start -p "$PROJECT_DIR" -c "$COLLECTION" 2>/dev/null || {
    # If session-start fails, show basic context
    EXIT_CODE=$?
    echo ""
    echo "=== Session Context ==="
    echo ""
    echo "System Health:"
    echo "  [WARN] Session check failed (exit code: $EXIT_CODE)"
    echo ""

    if command -v git &> /dev/null && [ -d "$PROJECT_DIR/.git" ]; then
        echo "Git Context:"
        BRANCH=$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
        echo "  Branch: $BRANCH"

        CHANGES=$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
        if [ "$CHANGES" -gt 0 ]; then
            echo "  Uncommitted: $CHANGES file(s)"
        fi
    fi

    echo ""
    echo "Memory-First Reminder:"
    echo "  Use mcp__${COLLECTION}-memory__search_similar() before reading files"
    echo "  Use mcp__${COLLECTION}-memory__read_graph() to understand relationships"
    echo ""

    # Always exit 0 - session start never blocks
    exit 0
}

# Exit with whatever code claude-indexer returned (0 or 1)
# Never exit 2 - session start never blocks
exit 0
