---
description: Diagnose testing debt (coverage, quality, reliability)
argument-hint: [count] [module-focus]
---

# Testing Debt Analysis

You are analyzing this codebase for **testing quality issues**. Find the top $1 issues (default: 3 if not specified).

**Module focus**: $2 (if specified, only analyze code related to this module/area)

**This command is part of the tech debt diagnosis suite:**
| Command | Focus | Level |
|---------|-------|-------|
| /refactor | SOLID, DRY, orphaned code | Function/class |
| /restructure | Cycles, coupling, stability | Module/architecture |
| /redocument | Coverage, usefulness, freshness | Documentation |
| /retest | Coverage, quality, reliability | Testing |

**Priority order**: Missing tests (Tier A) > Flaky tests > Weak assertions > Stale tests > Implementation coupling

---

## Testing Constitution (Core Principles)

1. **Critical code must have tests** - public APIs, complex logic, error paths
2. **Tests must be reliable** - no flakiness, no external dependencies
3. **Tests must be meaningful** - verify behavior, not implementation
4. **Tests must stay fresh** - update with code changes

---

## Scope Classification (Tier System)

### Tier A - FAIL if untested
Critical code requiring mandatory test coverage:
- Public API functions/methods
- Payment/financial logic
- Authentication/authorization
- Data validation
- Error handling paths

### Tier B - WARN if untested
Important code that should have tests:
- Business logic functions
- Data transformations
- Utility functions used widely
- Configuration parsing

### Tier C - INFO only
Lower priority for testing:
- Simple getters/setters
- Trivial glue code
- Framework-generated code

### Complexity Escalation Triggers
These bump requirements up a tier:
- Cyclomatic complexity > 10
- Multiple error handling branches
- Async/concurrent logic
- External service integration

---

## Analysis Protocol

Execute this multi-phase analysis using the memory MCP tools available to you.

### Phase 0: Module Focus (if specified)

If a module focus was provided (e.g., "payments", "auth", "api"):

1. **Discover related entities**: Use `search_similar("$2", limit=50)` to find all code related to the module
2. **Map the module boundary**: Use `read_graph(entity="<top_match>", mode="relationships")` for key entities
3. **Scope limitation**: ALL subsequent analysis phases only consider entities discovered here

**If no module focus**: Analyze the entire codebase.

---

### Phase 1: Coverage Analysis

1. Use `read_graph(mode="entities")` to get all code entities
2. For each entity, check for corresponding test file:
   - `src/module.py` → `tests/test_module.py`
   - `lib/service.js` → `tests/service.test.js`
3. Use `search_similar("test <function_name>", entityTypes=["function"])` to find specific tests
4. Flag Tier A entities without any test coverage

---

### Phase 2: Test Quality Analysis

1. Use `search_similar("assert", entityTypes=["function"])` in test directories
2. For each test function, evaluate assertions:
   - Count meaningful assertions vs `assert True` or `is not None`
   - Check for behavior verification vs implementation checking
3. Flag tests with weak or missing assertions

---

### Phase 3: Flakiness Detection

1. Search for flakiness indicators:
   - `search_similar("sleep time.sleep setTimeout", entityTypes=["function"])`
   - `search_similar("random mock.patch", entityTypes=["function"])`
2. Look for tests that:
   - Use timing-based assertions
   - Depend on external services
   - Use non-deterministic data
3. Check for `@pytest.mark.flaky` or similar markers

---

### Phase 4: Staleness Detection

1. Find tests referencing deleted code:
   - Tests importing non-existent modules
   - Tests calling removed functions
2. Find permanently skipped tests:
   - `@pytest.skip` without reason
   - `.skip()` or `xit()` in JS tests
3. Find tests for deprecated features

---

### Phase 5: Implementation Coupling Detection

1. Search for over-mocking patterns:
   - `search_similar("mock patch spy", entityTypes=["function"])`
2. Flag tests that:
   - Mock more than 3 internal functions
   - Assert on private method calls
   - Verify internal state rather than outputs

---

## Issue Categories

Report findings using these categories:

### [UNCOVERED] - Missing Test Coverage
```
[UNCOVERED] Critical public function has no tests
Symbol: process_payment() in payments/service.py:45
Tier: A (public API, async, handles money)
Risk: Changes could break payments silently
Suggestion: Add unit tests covering success, failure, and edge cases
```

### [WEAK] - Weak Assertions
```
[WEAK] Test has no meaningful assertions
Test: test_user_creation in tests/test_users.py:23
Problem: Only calls function, doesn't verify behavior
Current: assert True / assert user is not None
Suggestion: Assert specific properties, state changes, return values
```

### [FLAKY] - Flaky Tests
```
[FLAKY] Test relies on timing/randomness
Test: test_async_queue in tests/test_queue.py:89
Problem: Uses sleep(), random(), or external services
Failure rate: ~15% in CI
Suggestion: Mock time, use deterministic seeds, isolate external deps
```

### [STALE] - Stale Tests
```
[STALE] Test references deleted code
Test: test_legacy_parser in tests/test_parser.py:156
Problem: Tests LegacyParser which was removed 3 months ago
Suggestion: Delete test or update to test current implementation
```

### [MISSING] - Missing Test File
```
[MISSING] Module has no corresponding test file
Module: payments/refunds.py (450 lines, 12 functions)
Tier: A (public, handles money)
Suggestion: Create tests/test_refunds.py with coverage for public API
```

### [SKIPPED] - Unexplained Skips
```
[SKIPPED] Test skipped without explanation
Test: test_concurrent_writes in tests/test_db.py:234
Skip: @pytest.skip / .skip() / xit()
Problem: No comment explaining why or when to unskip
Suggestion: Add skip reason and ticket reference
```

### [IMPL] - Implementation-Coupled Tests
```
[IMPL] Test verifies implementation, not behavior
Test: test_user_save in tests/test_users.py:67
Problem: Mocks internals, asserts private method calls
Fragility: Will break on any refactor
Suggestion: Test observable behavior and outcomes instead
```

### [COMPLEX] - Complex Code Without Tests
```
[COMPLEX] Non-obvious code lacks corresponding tests
Symbol: parse_config() in config/parser.py:89
Triggers: regex, error handling, 15+ branches
Risk: High complexity with no safety net
Suggestion: Add tests covering each branch and error case
```

---

## Output Format

Present your findings as:

```
## Testing Quality Analysis

**Scope**: [Entire codebase | Focus: $2]
**Modules analyzed**: N
**Tier A coverage**: X% (Y/Z tested)
**Tier B coverage**: X% (Y/Z tested)

---

**Testing Issues Found:**

1. **[UNCOVERED]** `process_payment()` - Tier A function untested
   - Location: payments/service.py:45
   - Tier: A (public API, handles money)
   - Complexity: High (async, error handling)
   - Suggestion: Add unit tests for success, failure, edge cases

2. **[FLAKY]** `test_notification_queue` - Timing-dependent test
   - Location: tests/test_queue.py:89
   - Pattern: Uses time.sleep(5) for async wait
   - CI failure rate: ~15%
   - Suggestion: Use async testing utilities, mock time

3. **[WEAK]** `test_user_validation` - No meaningful assertions
   - Location: tests/test_users.py:34
   - Current: `assert result is not None`
   - Problem: Doesn't verify validation actually works
   - Suggestion: Assert specific validation rules applied

---

Which issues would you like me to address? Enter numbers (e.g., '1,3') or 'all':
```

---

## User Delegation

After presenting findings, ask the user which issues to address.

Based on their selection, take the appropriate action:

| Issue Type | Action |
|------------|--------|
| **[UNCOVERED]** | Generate test file/functions with comprehensive test cases |
| **[WEAK]** | Strengthen assertions to verify actual behavior |
| **[FLAKY]** | Refactor to remove timing/randomness dependencies |
| **[STALE]** | Delete obsolete tests or update for current code |
| **[MISSING]** | Create test file with skeleton tests for public API |
| **[SKIPPED]** | Add skip reason or implement the skipped test |
| **[IMPL]** | Refactor to test behavior instead of implementation |
| **[COMPLEX]** | Add comprehensive tests covering all branches |

For each selected issue:
1. **Analyze the code** to understand what tests are needed
2. **Generate appropriate tests** following existing test patterns in codebase
3. **Show the proposed tests** with clear descriptions
4. **Wait for user confirmation** before making changes

Wait for user input before making any changes.
