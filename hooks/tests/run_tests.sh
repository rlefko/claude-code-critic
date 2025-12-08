#!/bin/bash
# ============================================================================
# Memory Guard Test Runner
# ============================================================================
# Runs all test suites and reports results.
#
# Usage: ./run_tests.sh [test_file]
#   No args: run all tests
#   With arg: run specific test file
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD_SCRIPT="$SCRIPT_DIR/../pre-tool-guard.sh"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# === Test Framework ===

# Run guard with JSON input and capture results
run_guard() {
    local json="$1"
    local output
    local exit_code

    output=$(echo "$json" | "$GUARD_SCRIPT" 2>&1) || exit_code=$?
    exit_code=${exit_code:-0}

    echo "$exit_code:$output"
}

# Assert exit code matches expected
assert_exit() {
    local test_name="$1"
    local expected_exit="$2"
    local json="$3"

    TESTS_RUN=$((TESTS_RUN + 1))

    local result
    result=$(run_guard "$json")
    local actual_exit="${result%%:*}"
    local output="${result#*:}"

    if [[ "$actual_exit" == "$expected_exit" ]]; then
        echo -e "${GREEN}PASS${NC} $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC} $test_name"
        echo "  Expected exit: $expected_exit, Got: $actual_exit"
        echo "  Output: $output"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# Assert output contains expected string
assert_output_contains() {
    local test_name="$1"
    local expected_pattern="$2"
    local json="$3"

    TESTS_RUN=$((TESTS_RUN + 1))

    local result
    result=$(run_guard "$json")
    local output="${result#*:}"

    if echo "$output" | grep -qE "$expected_pattern"; then
        echo -e "${GREEN}PASS${NC} $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC} $test_name"
        echo "  Expected pattern: $expected_pattern"
        echo "  Output: $output"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# Assert exit code AND output pattern
assert_exit_and_output() {
    local test_name="$1"
    local expected_exit="$2"
    local expected_pattern="$3"
    local json="$4"

    TESTS_RUN=$((TESTS_RUN + 1))

    local result
    result=$(run_guard "$json")
    local actual_exit="${result%%:*}"
    local output="${result#*:}"

    local exit_ok=0
    local pattern_ok=0

    [[ "$actual_exit" == "$expected_exit" ]] && exit_ok=1
    echo "$output" | grep -qE "$expected_pattern" && pattern_ok=1

    if [[ $exit_ok -eq 1 && $pattern_ok -eq 1 ]]; then
        echo -e "${GREEN}PASS${NC} $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC} $test_name"
        [[ $exit_ok -eq 0 ]] && echo "  Expected exit: $expected_exit, Got: $actual_exit"
        [[ $pattern_ok -eq 0 ]] && echo "  Expected pattern not found: $expected_pattern"
        echo "  Output: $output"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# Export functions for test files
export -f run_guard assert_exit assert_output_contains assert_exit_and_output
export GUARD_SCRIPT RED GREEN YELLOW NC

# === Main ===

main() {
    echo "============================================"
    echo "Memory Guard Test Suite"
    echo "============================================"
    echo ""

    # Check guard exists
    if [[ ! -x "$GUARD_SCRIPT" ]]; then
        echo -e "${RED}ERROR${NC}: Guard script not found or not executable: $GUARD_SCRIPT"
        exit 1
    fi

    # Run tests
    if [[ $# -gt 0 ]]; then
        # Run specific test file
        if [[ -f "$SCRIPT_DIR/$1" ]]; then
            source "$SCRIPT_DIR/$1"
        else
            echo -e "${RED}ERROR${NC}: Test file not found: $1"
            exit 1
        fi
    else
        # Run all test files
        for test_file in "$SCRIPT_DIR"/test_*.sh; do
            if [[ -f "$test_file" ]]; then
                echo -e "${YELLOW}Running: $(basename "$test_file")${NC}"
                source "$test_file"
                echo ""
            fi
        done
    fi

    # Summary
    echo "============================================"
    echo "Results: $TESTS_PASSED/$TESTS_RUN passed"
    if [[ $TESTS_FAILED -gt 0 ]]; then
        echo -e "${RED}$TESTS_FAILED tests failed${NC}"
        exit 1
    else
        echo -e "${GREEN}All tests passed!${NC}"
        exit 0
    fi
}

main "$@"
