#!/bin/bash
# ============================================================================
# Performance Benchmark Tests for Memory Guard v4.1
# ============================================================================
#
# Tests the two-mode architecture performance:
#   - FAST mode (PreToolUse): Target <300ms
#   - FULL mode (pre-commit): No hard target, but tracked
#
# Usage:
#   ./hooks/tests/test_performance.sh
#
# Requirements:
#   - Python 3 with memory_guard.py and dependencies
#   - jq for JSON parsing
#   - bc for floating point math
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PRE_TOOL_GUARD="$PROJECT_ROOT/hooks/pre-tool-guard.sh"
MEMORY_GUARD="$PROJECT_ROOT/utils/memory_guard.py"

# Test configuration
FAST_MODE_TARGET_MS=300
ITERATIONS=3

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Counters
PASSED=0
FAILED=0
TOTAL=0

# Timing function (returns milliseconds)
time_ms() {
    local cmd="$1"
    local input="$2"

    # Use Python for precise timing since bash date doesn't have ms
    python3 << EOF
import subprocess
import time

start = time.perf_counter()
proc = subprocess.run(
    "$cmd",
    input='''$input''',
    capture_output=True,
    text=True,
    shell=True
)
end = time.perf_counter()
print(f'{(end - start) * 1000:.2f}')
EOF
}

# Test fast mode performance
test_fast_mode() {
    local description="$1"
    local input="$2"
    local target_ms="${3:-$FAST_MODE_TARGET_MS}"

    ((TOTAL++))

    echo -n "  Testing: $description... "

    # Run multiple iterations and average
    local total_ms=0
    local i

    for ((i=1; i<=ITERATIONS; i++)); do
        local ms
        ms=$(time_ms "python3 '$MEMORY_GUARD' --fast" "$input")
        total_ms=$(echo "$total_ms + $ms" | bc)
    done

    local avg_ms
    avg_ms=$(echo "scale=2; $total_ms / $ITERATIONS" | bc)

    # Check if within target
    local within_target
    within_target=$(echo "$avg_ms < $target_ms" | bc)

    if [[ "$within_target" -eq 1 ]]; then
        echo -e "${GREEN}PASS${NC} (${avg_ms}ms avg, target <${target_ms}ms)"
        ((PASSED++))
    else
        echo -e "${RED}FAIL${NC} (${avg_ms}ms avg, target <${target_ms}ms)"
        ((FAILED++))
    fi
}

# Test full mode (no target, just measure)
test_full_mode() {
    local description="$1"
    local input="$2"

    ((TOTAL++))

    echo -n "  Measuring: $description... "

    local ms
    ms=$(time_ms "python3 '$MEMORY_GUARD' --full" "$input")

    echo -e "${BLUE}${ms}ms${NC}"
    ((PASSED++))
}

# Test bash guard performance
test_bash_guard() {
    local description="$1"
    local input="$2"
    local target_ms="${3:-100}"

    ((TOTAL++))

    echo -n "  Testing: $description... "

    # Run multiple iterations
    local total_ms=0
    local i

    for ((i=1; i<=ITERATIONS; i++)); do
        local ms
        ms=$(time_ms "bash '$PRE_TOOL_GUARD'" "$input" 2>/dev/null || echo "100")
        total_ms=$(echo "$total_ms + $ms" | bc)
    done

    local avg_ms
    avg_ms=$(echo "scale=2; $total_ms / $ITERATIONS" | bc)

    # Check if within target
    local within_target
    within_target=$(echo "$avg_ms < $target_ms" | bc)

    if [[ "$within_target" -eq 1 ]]; then
        echo -e "${GREEN}PASS${NC} (${avg_ms}ms avg, target <${target_ms}ms)"
        ((PASSED++))
    else
        echo -e "${YELLOW}SLOW${NC} (${avg_ms}ms avg, target <${target_ms}ms)"
        ((FAILED++))
    fi
}

# Generate test inputs
generate_trivial_input() {
    cat << 'EOF'
{"tool_name": "Write", "tool_input": {"file_path": "/tmp/test.py", "content": "x = 1"}, "hook_event_name": "PreToolUse"}
EOF
}

generate_simple_function_input() {
    cat << 'EOF'
{"tool_name": "Write", "tool_input": {"file_path": "/tmp/test.py", "content": "def greet(name: str) -> str:\n    \"\"\"Greet someone.\"\"\"\n    return f\"Hello, {name}\""}, "hook_event_name": "PreToolUse"}
EOF
}

generate_complex_function_input() {
    cat << 'EOF'
{"tool_name": "Write", "tool_input": {"file_path": "/tmp/test.py", "content": "def process_data(items: list, config: dict) -> dict:\n    \"\"\"Process items according to config.\"\"\"\n    results = {}\n    for item in items:\n        if item.get('type') == 'A':\n            results[item['id']] = transform_a(item, config)\n        elif item.get('type') == 'B':\n            results[item['id']] = transform_b(item, config)\n        else:\n            results[item['id']] = item\n    return results"}, "hook_event_name": "PreToolUse"}
EOF
}

generate_security_issue_input() {
    cat << 'EOF'
{"tool_name": "Write", "tool_input": {"file_path": "/tmp/test.py", "content": "query = f\"SELECT * FROM users WHERE id={user_id}\""}, "hook_event_name": "PreToolUse"}
EOF
}

# Main test execution
main() {
    echo "=============================================="
    echo "Memory Guard v4.1 Performance Benchmarks"
    echo "=============================================="
    echo ""
    echo "Target: FAST mode < ${FAST_MODE_TARGET_MS}ms"
    echo "Iterations per test: $ITERATIONS"
    echo ""

    # Check prerequisites
    if [[ ! -f "$MEMORY_GUARD" ]]; then
        echo -e "${RED}ERROR: memory_guard.py not found${NC}"
        exit 1
    fi

    if ! command -v bc &>/dev/null; then
        echo -e "${RED}ERROR: bc is required for benchmarks${NC}"
        exit 1
    fi

    # === Tier 0 Tests (Trivial Operations) ===
    echo "--- Tier 0: Trivial Operations ---"
    test_fast_mode "Single variable assignment" "$(generate_trivial_input)" 50

    # === Tier 1 Tests (Bash Pattern Checks) ===
    echo ""
    echo "--- Tier 1: Pattern Checks (Bash) ---"
    test_bash_guard "Trivial input" "$(generate_trivial_input)" 100
    test_bash_guard "Security pattern (SQL injection)" "$(generate_security_issue_input)" 100

    # === Tier 2 Tests (Fast Duplicate Detection) ===
    echo ""
    echo "--- Tier 2: Fast Mode (Python) ---"
    test_fast_mode "Simple function" "$(generate_simple_function_input)" 300
    test_fast_mode "Complex function" "$(generate_complex_function_input)" 300

    # === Full Mode Tests (Reference Only) ===
    echo ""
    echo "--- Full Mode (Reference, No Target) ---"
    echo "  (These run Tier 3 Claude CLI - expected 5-30s)"
    # test_full_mode "Simple function" "$(generate_simple_function_input)"
    echo "  Skipped - would take too long for CI"

    # === Summary ===
    echo ""
    echo "=============================================="
    echo "Summary: $PASSED passed, $FAILED failed (of $TOTAL)"
    echo "=============================================="

    if [[ $FAILED -gt 0 ]]; then
        echo -e "${YELLOW}Some tests failed. Review timings above.${NC}"
        exit 1
    else
        echo -e "${GREEN}All performance targets met!${NC}"
        exit 0
    fi
}

main "$@"
