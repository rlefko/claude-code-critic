#!/bin/bash
# Post-file-change hook for Claude Code Memory
# Triggered after Write/Edit operations to keep memory index in sync
#
# Input: JSON via stdin with tool_name, tool_input (file_path, content, etc.)
# Exit codes:
#   0 = Success (message shown in verbose mode)
#   1 = Non-blocking error (shown to user)
#   2 = Blocking error (shown to Claude) - not used here since this is post-hook

# Read JSON input from stdin
INPUT=$(cat)

# Extract file path from tool input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Skip if no file path (shouldn't happen for Write/Edit)
if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Skip non-code files
case "$FILE_PATH" in
    *.log|*.tmp|*.bak|*.swp|*.pyc|*.pyo|__pycache__/*|.git/*|node_modules/*|.venv/*|.claude/*|.index_cache/*)
        exit 0
        ;;
esac

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

# Get project root from file path
PROJECT_DIR=$(find_project_root "$(dirname "$FILE_PATH")")
if [ -z "$PROJECT_DIR" ]; then
    # Fallback to current directory
    PROJECT_DIR=$(pwd)
fi

# Get collection name from environment (set by setup.sh)
COLLECTION="${CLAUDE_MEMORY_COLLECTION:-}"

if [ -z "$COLLECTION" ]; then
    # Try to read from .mcp.json in project directory
    if [ -f "$PROJECT_DIR/.mcp.json" ]; then
        COLLECTION=$(jq -r '.mcpServers | keys[0] | sub("-memory$"; "")' "$PROJECT_DIR/.mcp.json" 2>/dev/null)
    fi
fi

# If still no collection, skip silently
if [ -z "$COLLECTION" ]; then
    exit 0
fi

# Check if claude-indexer is available
if ! command -v claude-indexer &> /dev/null; then
    # Not installed globally, skip silently
    exit 0
fi

# Use single-file indexing (fast ~100ms) instead of full project index
# The 'file' command indexes just one file efficiently
claude-indexer file -p "$PROJECT_DIR" -c "$COLLECTION" "$FILE_PATH" --quiet 2>/dev/null

# Always succeed - this is a post-hook, we don't want to block
exit 0
