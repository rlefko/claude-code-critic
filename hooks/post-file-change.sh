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
    *.log|*.tmp|*.bak|*.swp|*.pyc|*.pyo|__pycache__/*|.git/*|node_modules/*|.venv/*)
        exit 0
        ;;
esac

# Get collection name from environment (set by setup.sh)
COLLECTION="${CLAUDE_MEMORY_COLLECTION:-}"

if [ -z "$COLLECTION" ]; then
    # Try to read from .mcp.json in current directory
    if [ -f ".mcp.json" ]; then
        COLLECTION=$(jq -r '.mcpServers | keys[0] | sub("-memory$"; "")' .mcp.json 2>/dev/null)
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

# Queue the file for indexing (async, non-blocking)
# Using a simple approach: just run indexer on the single file's directory
PROJECT_DIR=$(pwd)

# Run indexer in background to avoid blocking Claude
(claude-indexer index -p "$PROJECT_DIR" -c "$COLLECTION" --quiet 2>/dev/null &)

# Always succeed - this is a post-hook, we don't want to block
exit 0
