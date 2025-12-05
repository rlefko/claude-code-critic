---
description: Diagnose resilience issues (error handling, retries, fallbacks)
argument-hint: [count] [module-focus]
---

# Resilience Debt Analysis

You are analyzing this codebase for **resilience issues**. Find the top $1 issues (default: 3 if not specified).

**Module focus**: $2 (if specified, only analyze code related to this module/area)

**This command is part of the tech debt diagnosis suite:**
| Command | Focus | Level |
|---------|-------|-------|
| /refactor | SOLID, DRY, orphaned code | Function/class |
| /reresilience | Error handling, retries, fallbacks | Resilience |
| /resecure | Secrets, injection, validation | Security |

**Priority order**: Swallowed exceptions > Missing timeouts > Missing retries > Generic handlers > Missing fallbacks > Unlogged errors

---

## Resilience Constitution (Core Principles)

1. **Expect failures** - external services will fail, network will hiccup
2. **Fail fast** - detect problems early, don't hide them
3. **Recover gracefully** - retries, fallbacks, graceful degradation
4. **Maintain visibility** - log errors with context for debugging

---

## Risk Classification

### CRITICAL - Silent data loss or corruption risk
- Exceptions caught and ignored (`except: pass`)
- Errors converted to success responses
- Missing transaction rollback

### HIGH - Service degradation risk
- No timeout on external calls
- No retry for transient failures
- Cascade failure potential

### MEDIUM - Debugging difficulty
- Generic catch-all handlers
- Errors not logged
- Missing context in error messages

### LOW - Non-critical issues
- Missing circuit breakers
- Suboptimal retry strategies
- Verbose error handling

---

## Analysis Protocol

Execute this multi-phase analysis using the memory MCP tools available to you.

### Phase 0: Module Focus (if specified)

If a module focus was provided (e.g., "integrations", "api", "sync"):

1. **Discover related entities**: Use `search_similar("$2", limit=50)` to find all code related to the module
2. **Map the module boundary**: Use `read_graph(entity="<top_match>", mode="relationships")` for key entities
3. **Scope limitation**: ALL subsequent analysis phases only consider entities discovered here

**If no module focus**: Analyze the entire codebase.

---

### Phase 1: Swallowed Exception Detection

1. Search for empty exception handlers:
   - `search_similar("except pass except Exception", entityTypes=["function"])`
2. Look for patterns:
   - `except: pass`
   - `except Exception: pass`
   - `except Exception as e: pass`
   - `.catch(() => {})`
3. Flag silent failure points

---

### Phase 2: Generic Handler Detection

1. Find broad exception catching:
   - `search_similar("except Exception catch error", entityTypes=["function"])`
2. Flag handlers that:
   - Catch all exceptions without specific handling
   - Return generic error messages
   - Don't distinguish error types

---

### Phase 3: Missing Timeout Detection

1. Find external service calls:
   - `search_similar("requests http fetch api call", entityTypes=["function"])`
2. Check for timeout parameters:
   - `requests.get(url)` without `timeout=`
   - `fetch()` without `AbortController`
   - Database queries without timeout
3. Flag calls that can hang indefinitely

---

### Phase 4: Missing Retry Detection

1. Find calls to unreliable services:
   - `search_similar("external api webhook payment stripe", entityTypes=["function"])`
2. Check for retry logic:
   - Retry decorator/wrapper
   - Exponential backoff
   - Max attempts limit
3. Flag one-shot calls that should retry

---

### Phase 5: Missing Fallback Detection

1. Find critical dependencies:
   - `search_similar("service client integration", entityTypes=["class"])`
2. Check for fallback behavior:
   - Graceful degradation
   - Cached responses
   - Default values
3. Flag dependencies without fallback

---

### Phase 6: Error Logging Gaps

1. Find exception handlers:
   - `search_similar("except catch error handle", entityTypes=["function"])`
2. Check for logging:
   - `logger.error()` or equivalent
   - Context information (what failed, inputs)
   - Stack trace preservation
3. Flag unlogged errors

---

## Issue Categories

Report findings using these categories:

### [SWALLOW] - Swallowed Exceptions
```
[SWALLOW] Exception caught and ignored
Location: sync/worker.py:89
Code: except Exception: pass
Problem: Silent failures hide bugs
Suggestion: Log error, re-raise, or handle specifically
```

### [GENERIC] - Generic Error Handler
```
[GENERIC] Catch-all exception handler
Location: api/handlers.py:34
Code: except Exception as e: return {"error": "Something went wrong"}
Problem: Hides specific errors, makes debugging hard
Suggestion: Handle specific exceptions with specific responses
```

### [RETRY] - Missing Retry Logic
```
[RETRY] Transient failure without retry
Location: integrations/payment.py:67
Code: response = stripe.charge()  # can fail transiently
Risk: Temporary network issues cause permanent failures
Suggestion: Add retry with exponential backoff for transient errors
```

### [TIMEOUT] - Missing Timeout
```
[TIMEOUT] External call without timeout
Location: services/geocode.py:45
Code: requests.get(url)  # no timeout parameter
Risk: Hung request blocks thread indefinitely
Suggestion: Add timeout: requests.get(url, timeout=5)
```

### [CIRCUIT] - Missing Circuit Breaker
```
[CIRCUIT] Repeated calls to failing service
Location: integrations/inventory.py:89
Pattern: No circuit breaker on external API
Risk: Cascade failures when dependency is down
Suggestion: Add circuit breaker pattern with fallback
```

### [FALLBACK] - Missing Fallback
```
[FALLBACK] No fallback for critical dependency
Location: features/recommendations.py:34
Dependency: ML service (external)
Risk: Feature completely fails when ML service is down
Suggestion: Add fallback to rule-based recommendations
```

### [PROPAGATE] - Error Not Propagated
```
[PROPAGATE] Error converted to success
Location: orders/checkout.py:123
Code: if payment_failed: return {"status": "pending"}
Problem: Caller thinks operation succeeded
Suggestion: Return error status or raise exception
```

### [LOG] - Error Not Logged
```
[LOG] Exception handled without logging
Location: background/tasks.py:67
Code: except APIError as e: retry()
Problem: No visibility into failure patterns
Suggestion: Log error with context before retry
```

---

## Output Format

Present your findings as:

```
## Resilience Analysis

**Scope**: [Entire codebase | Focus: $2]
**Functions analyzed**: N
**Critical issues**: X
**High risk**: Y
**Medium risk**: Z

---

**Resilience Issues Found:**

1. **[CRITICAL]** [SWALLOW] Silent exception in payment processing
   - Location: payments/processor.py:89
   - Code: `except Exception: pass`
   - Risk: Payment failures go unnoticed
   - Suggestion: Log error, alert on-call, return error to caller

2. **[HIGH]** [TIMEOUT] External API call without timeout
   - Location: integrations/shipping.py:45
   - Code: `requests.post(carrier_api, data)`
   - Risk: Thread blocked indefinitely if API hangs
   - Suggestion: Add `timeout=30` parameter

3. **[MEDIUM]** [GENERIC] Catch-all hiding specific errors
   - Location: api/orders.py:123
   - Code: `except Exception: return {"error": "Failed"}`
   - Impact: Can't distinguish validation vs database vs network errors
   - Suggestion: Handle ValidationError, DatabaseError separately

---

Which issues would you like me to address? Enter numbers (e.g., '1,3') or 'all':
```

---

## User Delegation

After presenting findings, ask the user which issues to address.

Based on their selection, take the appropriate action:

| Issue Type | Action |
|------------|--------|
| **[SWALLOW]** | Add proper error handling with logging |
| **[GENERIC]** | Split into specific exception handlers |
| **[RETRY]** | Add retry decorator with backoff |
| **[TIMEOUT]** | Add appropriate timeout parameter |
| **[CIRCUIT]** | Implement circuit breaker pattern |
| **[FALLBACK]** | Add fallback behavior for degraded mode |
| **[PROPAGATE]** | Fix to properly indicate failure |
| **[LOG]** | Add logging with appropriate context |

For each selected issue:
1. **Analyze the code** to understand the failure modes
2. **Generate resilient replacement** following best practices
3. **Show the proposed fix** with resilience explanation
4. **Wait for user confirmation** before making changes

Wait for user input before making any changes.
