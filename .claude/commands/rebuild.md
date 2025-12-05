---
description: Meta-analysis of ALL tech debt dimensions (most critical issues)
argument-hint: [count] [module-focus]
---

# Tech Debt Meta-Analysis

You are performing a **comprehensive tech debt analysis** across ALL dimensions. Find the top $1 most critical issues (default: 10 if not specified).

**Module focus**: $2 (if specified, only analyze code related to this module/area)

**This is the meta-command that spans all tech debt diagnosis tools:**
| Command | Dimension | Weight |
|---------|-----------|--------|
| /resecure | Security | 100 (Critical) |
| /retest | Testing | 70 |
| /reresilience | Resilience | 60 |
| /restructure | Architecture | 50 |
| /retype | Type Safety | 40 |
| /reoptimize | Performance | 35 |
| /refactor | Code Quality | 30 |
| /redocument | Documentation | 30 |
| /resolve | Explicit Debt | 25 |

---

## Meta-Analysis Constitution (Core Principles)

1. **Security trumps all** - vulnerabilities are always highest priority
2. **Testing enables everything** - untested code can't be safely changed
3. **Resilience protects users** - graceful failure beats silent corruption
4. **Prioritize by impact** - fix what affects users most

---

## Scoring Matrix

Each issue is scored by: `Category Weight × Severity Multiplier × Tier Multiplier`

### Severity Multipliers
| Severity | Multiplier |
|----------|------------|
| CRITICAL | 1.0 |
| HIGH | 0.7 |
| MEDIUM | 0.4 |
| LOW | 0.15 |

### Tier Multipliers (for tiered categories)
| Tier | Multiplier |
|------|------------|
| A | 1.0 |
| B | 0.6 |
| C | 0.2 |

### Example Scores
- Security CRITICAL = 100 × 1.0 = **100**
- Testing HIGH (Tier A) = 70 × 0.7 × 1.0 = **49**
- Architecture HIGH = 50 × 0.7 = **35**
- Documentation MEDIUM (Tier A) = 30 × 0.4 × 1.0 = **12**

---

## Analysis Protocol

Execute a multi-dimensional analysis using the memory MCP tools available to you.

### Phase 0: Module Focus (if specified)

If a module focus was provided:

1. **Discover related entities**: Use `search_similar("$2", limit=50)` to find all code related to the module
2. **Map the module boundary**: Use `read_graph(entity="<top_match>", mode="relationships")` for key entities
3. **Scope limitation**: ALL subsequent analysis phases only consider entities discovered here

**If no module focus**: Analyze the entire codebase.

---

### Phase 1: Security Scan (Weight: 100)

Run security analysis looking for:
- Hardcoded secrets [CRITICAL]
- Injection vulnerabilities [CRITICAL/HIGH]
- Missing authentication [HIGH]
- Weak cryptography [MEDIUM]
- Input validation gaps [MEDIUM]

Use: `search_similar("password secret key token", entityTypes=["function"])`
Use: `search_similar("SELECT INSERT query execute", entityTypes=["function"])`

---

### Phase 2: Testing Gaps (Weight: 70)

Run testing analysis looking for:
- Untested Tier A code [HIGH]
- Flaky tests [HIGH]
- Weak assertions [MEDIUM]
- Missing test files [MEDIUM]

Use: `search_similar("test assert mock", entityTypes=["function"])`

---

### Phase 3: Resilience Issues (Weight: 60)

Run resilience analysis looking for:
- Swallowed exceptions [CRITICAL]
- Missing timeouts [HIGH]
- Missing retries [HIGH]
- Generic handlers [MEDIUM]

Use: `search_similar("except catch error timeout", entityTypes=["function"])`

---

### Phase 4: Architecture Problems (Weight: 50)

Run architecture analysis looking for:
- Circular dependencies [HIGH]
- Unstable abstractions [HIGH]
- High coupling [MEDIUM]
- Cohesion issues [MEDIUM]

Use: `read_graph(mode="relationships")` to analyze dependency structure

---

### Phase 5: Type Safety (Weight: 40)

Run type safety analysis looking for:
- Untyped public APIs [HIGH]
- Any overuse [MEDIUM]
- Unsafe casts [MEDIUM]
- Nullable mishandling [MEDIUM]

Use: `search_similar("Any unknown def function", entityTypes=["function"])`

---

### Phase 6: Performance Issues (Weight: 35)

Run performance analysis looking for:
- N+1 queries [HIGH]
- Blocking in async [HIGH]
- Missing caching [MEDIUM]
- Inefficient algorithms [MEDIUM]

Use: `search_similar("for loop query fetch async", entityTypes=["function"])`

---

### Phase 7: Code Quality (Weight: 30)

Run code quality analysis looking for:
- SOLID violations [HIGH]
- DRY violations [MEDIUM]
- Orphaned code [LOW]
- Convention violations [LOW]

Use: `read_graph(mode="entities")` and `get_implementation()` for analysis

---

### Phase 8: Documentation Gaps (Weight: 30)

Run documentation analysis looking for:
- Undocumented Tier A [HIGH]
- Stale documentation [MEDIUM]
- Tautological docs [LOW]

Use: `get_implementation(name, scope="logical")` to check docstrings

---

### Phase 9: Explicit Debt (Weight: 25)

Run explicit debt analysis looking for:
- FIXME markers [HIGH]
- HACK markers [MEDIUM]
- Old TODOs [MEDIUM]
- DEPRECATED in use [LOW]

Use: `search_similar("TODO FIXME HACK DEPRECATED", entityTypes=["function"])`

---

## Output Format

Present your findings as:

```
## Tech Debt Meta-Analysis

**Scope**: [Entire codebase | Focus: $2]
**Health Score**: XX/100
**Total Issues Found**: N across 9 dimensions

### Issue Distribution

| Dimension | Critical | High | Medium | Low | Score Impact |
|-----------|----------|------|--------|-----|--------------|
| Security | 2 | 3 | 5 | 2 | -45 |
| Testing | 1 | 5 | 10 | 8 | -32 |
| Resilience | 0 | 4 | 8 | 5 | -25 |
| Architecture | 0 | 2 | 6 | 3 | -18 |
| Types | 0 | 3 | 12 | 15 | -15 |
| Performance | 0 | 2 | 5 | 8 | -12 |
| Code Quality | 0 | 1 | 8 | 12 | -10 |
| Documentation | 0 | 2 | 10 | 20 | -8 |
| Explicit Debt | 0 | 4 | 15 | 25 | -7 |

---

### Top 10 Most Critical Issues

1. **Score: 100** [SECRET] Hardcoded API key
   - Dimension: Security (CRITICAL)
   - Location: config/stripe.py:12
   - Risk: Production credentials exposed in source
   - Action: Move to environment variable immediately

2. **Score: 100** [INJECT] SQL injection vulnerability
   - Dimension: Security (CRITICAL)
   - Location: users/search.py:45
   - Risk: Arbitrary database access
   - Action: Use parameterized queries

3. **Score: 70** [SWALLOW] Silent exception in payments
   - Dimension: Resilience (CRITICAL)
   - Location: payments/processor.py:89
   - Risk: Payment failures go unnoticed
   - Action: Add logging and error propagation

4. **Score: 49** [UNCOVERED] Payment logic untested
   - Dimension: Testing (HIGH, Tier A)
   - Location: payments/calculator.py
   - Risk: Financial bugs undetected
   - Action: Add comprehensive test suite

5. **Score: 35** [CYCLE] Circular dependency
   - Dimension: Architecture (HIGH)
   - Location: auth ↔ users ↔ permissions
   - Impact: 23 files affected
   - Action: Extract shared interface module

...

---

### Quick Wins (High Impact, Low Effort)

1. Add timeout to 5 HTTP calls (~30 min)
2. Move 3 hardcoded secrets to env vars (~15 min)
3. Add 2 missing auth decorators (~20 min)

### Major Projects (Requires Planning)

1. **Testing Debt**: 12 untested Tier A functions
   - Estimated: 2-3 days of focused work

2. **Architecture**: Circular dependency in core modules
   - Estimated: 1 day of careful refactoring

3. **Security**: Input validation audit
   - Estimated: 1 day to audit, 2-3 days to fix

---

Which issues would you like me to address?
- Enter numbers (e.g., '1,3,5') for specific issues
- Enter 'quick' for all quick wins
- Enter 'security' for all security issues
- Enter 'all' for everything
```

---

## User Delegation

After presenting findings, ask the user which issues to address.

Based on their selection:

| Selection | Action |
|-----------|--------|
| Specific numbers | Address those specific issues in priority order |
| 'quick' | Address all quick wins in sequence |
| 'security' | Address all security issues first |
| 'testing' | Focus on testing gaps |
| 'all' | Work through all issues by priority |

For each selected issue:
1. **Navigate to the specific issue type's fix strategy**
2. **Generate appropriate fix** following that dimension's patterns
3. **Show the proposed change** with impact explanation
4. **Wait for user confirmation** before making changes

Wait for user input before making any changes.
