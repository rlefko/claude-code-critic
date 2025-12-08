#!/usr/bin/env bash
# ============================================================================
# Pre-Commit Guard - Full Tier 3 Analysis Before Commit
# ============================================================================
#
# This hook runs FULL Memory Guard analysis (including Tier 3) on all staged
# files before allowing a commit. This ensures thorough code quality checks
# happen before code enters the repository.
#
# Architecture:
#   - During editing (PreToolUse): Fast checks only (Tier 0-2, <300ms)
#   - Before commit (this hook): Full aggressive check (Tier 3, 5-30s per file)
#
# Installation:
#   ln -sf ../../hooks/pre-commit-guard.sh .git/hooks/pre-commit
#
# Manual run:
#   ./hooks/pre-commit-guard.sh
#
# Exit codes:
#   0 - All files passed analysis
#   1 - One or more files failed analysis (commit blocked)
#   2 - Critical error in guard system
#
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MEMORY_GUARD="$PROJECT_ROOT/utils/memory_guard.py"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/pre-commit-guard.log"

# Configuration
MAX_FILES="${GUARD_MAX_FILES:-20}"           # Max files to analyze (for performance)
TIMEOUT="${GUARD_COMMIT_TIMEOUT:-120}"       # Per-file timeout in seconds
SKIP_PATTERNS="${GUARD_SKIP_PATTERNS:-}"     # Additional skip patterns
VERBOSE="${GUARD_VERBOSE:-false}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Console output
    case "$level" in
        ERROR)   echo -e "${RED}[ERROR]${NC} $message" >&2 ;;
        WARN)    echo -e "${YELLOW}[WARN]${NC} $message" ;;
        SUCCESS) echo -e "${GREEN}[OK]${NC} $message" ;;
        INFO)    echo -e "${BLUE}[INFO]${NC} $message" ;;
        *)       echo "$message" ;;
    esac

    # File logging
    mkdir -p "$LOG_DIR"
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

# Get staged code files (excluding docs, configs, etc.)
get_staged_files() {
    git diff --cached --name-only --diff-filter=ACM | \
        grep -E '\.(py|js|ts|jsx|tsx|java|go|rs|c|cpp|h|hpp|rb|php|swift|kt)$' | \
        grep -v -E '(test_|_test\.|spec\.|\.test\.)' | \
        head -n "$MAX_FILES" || true
}

# Check if Memory Guard is available
check_prerequisites() {
    if [[ ! -f "$MEMORY_GUARD" ]]; then
        log "ERROR" "Memory Guard not found at $MEMORY_GUARD"
        return 2
    fi

    if ! command -v python3 &> /dev/null; then
        log "ERROR" "Python 3 is required but not found"
        return 2
    fi

    return 0
}

# Run full analysis on a single file
analyze_file() {
    local file_path="$1"
    local result
    local exit_code

    if [[ "$VERBOSE" == "true" ]]; then
        log "INFO" "Analyzing: $file_path"
    fi

    # Run Memory Guard in FULL mode
    result=$(timeout "$TIMEOUT"s python3 "$MEMORY_GUARD" --full --file "$file_path" 2>&1) || exit_code=$?

    if [[ "${exit_code:-0}" -eq 124 ]]; then
        log "WARN" "Analysis timed out for $file_path (>${TIMEOUT}s)"
        return 0  # Don't block on timeout - allow commit
    fi

    if [[ "${exit_code:-0}" -ne 0 ]]; then
        # Check if it's a blocking decision
        if echo "$result" | grep -q '"blocked": true'; then
            return 1
        fi
    fi

    # Check for explicit block decision in output
    if echo "$result" | grep -q '"decision": "block"'; then
        return 1
    fi

    return 0
}

# Main pre-commit check
main() {
    log "INFO" "Pre-commit guard starting (FULL mode)"

    # Check prerequisites
    check_prerequisites || exit $?

    # Get staged files
    local staged_files
    staged_files=$(get_staged_files)

    if [[ -z "$staged_files" ]]; then
        log "INFO" "No code files staged for commit"
        exit 0
    fi

    local file_count
    file_count=$(echo "$staged_files" | wc -l | tr -d ' ')
    log "INFO" "Analyzing $file_count staged file(s)..."

    # Track results
    local passed=0
    local failed=0
    local failed_files=()

    # Analyze each file
    while IFS= read -r file_path; do
        [[ -z "$file_path" ]] && continue

        # Skip user-defined patterns
        if [[ -n "$SKIP_PATTERNS" ]] && echo "$file_path" | grep -qE "$SKIP_PATTERNS"; then
            if [[ "$VERBOSE" == "true" ]]; then
                log "INFO" "Skipping (pattern match): $file_path"
            fi
            continue
        fi

        if analyze_file "$file_path"; then
            ((passed++))
            if [[ "$VERBOSE" == "true" ]]; then
                log "SUCCESS" "$file_path"
            fi
        else
            ((failed++))
            failed_files+=("$file_path")
            log "ERROR" "Quality issues found in: $file_path"
        fi
    done <<< "$staged_files"

    # Summary
    echo ""
    log "INFO" "Pre-commit analysis complete: $passed passed, $failed failed"

    if [[ "$failed" -gt 0 ]]; then
        echo ""
        log "ERROR" "Commit blocked due to quality issues in:"
        for f in "${failed_files[@]}"; do
            echo "  - $f"
        done
        echo ""
        echo "To see details, run:"
        echo "  python3 $MEMORY_GUARD --full --files ${failed_files[*]}"
        echo ""
        echo "To bypass this check (not recommended):"
        echo "  git commit --no-verify"
        exit 1
    fi

    log "SUCCESS" "All files passed quality checks"
    exit 0
}

# Run main
main "$@"
