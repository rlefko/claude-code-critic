#!/bin/bash
# ============================================================================
# install-git-hooks.sh - Reinstall Memory Git Hooks
# ============================================================================
#
# Use this script to reinstall git hooks if they get overridden by other tools.
# Run from the project root directory.
#
# Usage:
#   ./.claude/scripts/install-git-hooks.sh [collection-name]
#
# If collection-name is not provided, attempts to detect from existing hooks.
#
# ============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1" >&2; }
print_warning() { echo -e "${YELLOW}!${NC} $1"; }
print_info() { echo -e "${BLUE}ℹ${NC} $1"; }

# Find project root (look for .git directory)
find_project_root() {
    local dir="$PWD"
    while [ "$dir" != "/" ]; do
        if [ -d "$dir/.git" ]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    return 1
}

PROJECT_ROOT=$(find_project_root) || {
    print_error "Not in a git repository"
    exit 1
}

HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
COLLECTION_NAME="${1:-}"

# Try to detect collection name from existing hooks
if [ -z "$COLLECTION_NAME" ]; then
    if [ -f "$HOOKS_DIR/post-merge" ]; then
        COLLECTION_NAME=$(grep "Collection:" "$HOOKS_DIR/post-merge" 2>/dev/null | sed 's/.*Collection: //' || echo "")
    fi
fi

if [ -z "$COLLECTION_NAME" ]; then
    # Derive from project directory name
    COLLECTION_NAME=$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
    print_warning "Collection name not found, using: $COLLECTION_NAME"
fi

print_info "Installing git hooks for collection: $COLLECTION_NAME"
print_info "Project root: $PROJECT_ROOT"

# Create pre-commit hook (Tier 3 Memory Guard + batch indexing)
print_info "Creating pre-commit hook..."
cat > "$HOOKS_DIR/pre-commit" << 'HOOK_EOF'
#!/bin/bash
# Semantic Code Memory - Pre-commit Hook
# Tier 3 Memory Guard + Batch indexing
# Collection: COLLECTION_PLACEHOLDER

# Run Tier 3 guard first (full analysis before commit)
GUARD_SCRIPT="$(git rev-parse --show-toplevel)/.claude/hooks/pre-commit-guard.sh"
if [ -x "$GUARD_SCRIPT" ]; then
    echo "🛡️  Running Memory Guard (Tier 3)..."
    if ! "$GUARD_SCRIPT"; then
        echo "❌ Pre-commit guard failed"
        exit 1
    fi
fi

# Then do batch indexing
echo "🔄 Indexing staged files..."

# Get staged files (Added, Copied, Modified - not Deleted)
# Filter to only existing files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | while read -r f; do [ -f "$f" ] && echo "$f"; done)

if [ -z "$STAGED_FILES" ]; then
    echo "✅ No files to index"
    exit 0
fi

FILE_COUNT=$(echo "$STAGED_FILES" | wc -l | tr -d ' ')
echo "📁 Batch indexing $FILE_COUNT file(s)..."

# Pipe files to batch indexer (single process, shared embeddings)
echo "$STAGED_FILES" | claude-indexer index -p "$(pwd)" -c "COLLECTION_PLACEHOLDER" --files-from-stdin --quiet

if [ $? -eq 0 ]; then
    echo "✅ Indexed $FILE_COUNT file(s)"
else
    echo "⚠️  Some files failed to index"
fi

# Always allow commit to proceed
exit 0
HOOK_EOF
sed -i '' "s/COLLECTION_PLACEHOLDER/$COLLECTION_NAME/g" "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-commit"
print_success "Pre-commit hook installed (Tier 3 guard + batch indexing)"

# Create post-merge hook
print_info "Creating post-merge hook..."
cat > "$HOOKS_DIR/post-merge" << 'HOOK_EOF'
#!/bin/bash
# Semantic Code Memory - Post-merge Hook
# Batch index merged files using --files-from-stdin (4-15x faster)
# Collection: COLLECTION_PLACEHOLDER

echo "🔄 Indexing merged files..."

# Get files changed by the merge, filter to only existing files
CHANGED_FILES=$(git diff --name-only HEAD@{1} HEAD 2>/dev/null | while read -r f; do [ -f "$f" ] && echo "$f"; done)

if [ -z "$CHANGED_FILES" ]; then
    echo "✅ No files to index"
    exit 0
fi

FILE_COUNT=$(echo "$CHANGED_FILES" | wc -l | tr -d ' ')
echo "📁 Batch indexing $FILE_COUNT file(s)..."

# Pipe files to batch indexer (single process, shared embeddings)
echo "$CHANGED_FILES" | claude-indexer index -p "$(pwd)" -c "COLLECTION_PLACEHOLDER" --files-from-stdin --quiet

if [ $? -eq 0 ]; then
    echo "✅ Indexed $FILE_COUNT file(s)"
else
    echo "⚠️  Some files failed to index"
fi

# Always allow operation to proceed
exit 0
HOOK_EOF
sed -i '' "s/COLLECTION_PLACEHOLDER/$COLLECTION_NAME/g" "$HOOKS_DIR/post-merge"
chmod +x "$HOOKS_DIR/post-merge"
print_success "Post-merge hook installed"

# Create post-checkout hook
print_info "Creating post-checkout hook..."
cat > "$HOOKS_DIR/post-checkout" << 'HOOK_EOF'
#!/bin/bash
# Semantic Code Memory - Post-checkout Hook
# Batch index changed files using --files-from-stdin (4-15x faster)
# Collection: COLLECTION_PLACEHOLDER

prev_head=$1
new_head=$2
branch_checkout=$3

# Only run on branch checkouts (not file checkouts)
[ "$branch_checkout" != "1" ] && exit 0

echo "🔄 Indexing changed files..."

# Handle initial checkout (prev_head is all zeros)
if [ "$prev_head" = "0000000000000000000000000000000000000000" ]; then
    echo "Initial checkout detected, running full index..."
    claude-indexer index -p "$(pwd)" -c "COLLECTION_PLACEHOLDER" --quiet 2>&1 | grep -E "(✓|✗)" || true
    exit 0
fi

# Get all changed files between commits
ALL_CHANGED=$(git diff --name-only "$prev_head" "$new_head" 2>/dev/null)

if [ -z "$ALL_CHANGED" ]; then
    echo "✅ No files changed between branches"
    exit 0
fi

# Separate into files that exist vs don't exist
EXISTING_FILES=""
REMOVED_COUNT=0

while IFS= read -r f; do
    [ -z "$f" ] && continue
    if [ -f "$f" ]; then
        EXISTING_FILES="${EXISTING_FILES}${f}"$'\n'
    else
        REMOVED_COUNT=$((REMOVED_COUNT + 1))
    fi
done <<< "$ALL_CHANGED"

# Trim trailing newline
EXISTING_FILES="${EXISTING_FILES%$'\n'}"

# Handle case where only files were removed (no files to index)
if [ -z "$EXISTING_FILES" ]; then
    if [ "$REMOVED_COUNT" -gt 0 ]; then
        echo "✅ $REMOVED_COUNT file(s) no longer exist on this branch"
    else
        echo "✅ No files to index"
    fi
    exit 0
fi

# Index existing files
FILE_COUNT=$(echo "$EXISTING_FILES" | wc -l | tr -d ' ')
echo "📁 Batch indexing $FILE_COUNT file(s)..."
if [ "$REMOVED_COUNT" -gt 0 ]; then
    echo "ℹ️  $REMOVED_COUNT file(s) no longer exist on this branch"
fi

# Pipe files to batch indexer (single process, shared embeddings)
echo "$EXISTING_FILES" | claude-indexer index -p "$(pwd)" -c "COLLECTION_PLACEHOLDER" --files-from-stdin --quiet

if [ $? -eq 0 ]; then
    echo "✅ Indexed $FILE_COUNT file(s)"
else
    echo "⚠️  Some files failed to index"
fi

# Always allow operation to proceed
exit 0
HOOK_EOF
sed -i '' "s/COLLECTION_PLACEHOLDER/$COLLECTION_NAME/g" "$HOOKS_DIR/post-checkout"
chmod +x "$HOOKS_DIR/post-checkout"
print_success "Post-checkout hook installed"

echo ""
print_success "All git hooks installed!"
echo ""
print_info "Hooks installed:"
print_info "  - pre-commit: Tier 3 Memory Guard + batch indexing"
print_info "  - post-merge: Batch index merged files"
print_info "  - post-checkout: Batch index changed files"
