---
description: Diagnose performance issues (N+1, caching, algorithms)
argument-hint: [count] [module-focus]
---

# Performance Debt Analysis

You are analyzing this codebase for **performance issues**. Find the top $1 issues (default: 3 if not specified).

**Module focus**: $2 (if specified, only analyze code related to this module/area)

**This command is part of the tech debt diagnosis suite:**
| Command | Focus | Level |
|---------|-------|-------|
| /refactor | SOLID, DRY, orphaned code | Function/class |
| /reoptimize | N+1, caching, algorithms | Performance |
| /reresilience | Error handling, retries | Resilience |

**Priority order**: N+1 queries > Blocking sync ops > Missing cache > Inefficient algorithms > Memory issues > Missing indexes

---

## Performance Constitution (Core Principles)

1. **Avoid premature optimization** - but fix obvious inefficiencies
2. **Measure before optimizing** - don't guess at bottlenecks
3. **O(n) beats O(n²)** - algorithmic improvements trump micro-optimizations
4. **Cache expensive operations** - but invalidate correctly

---

## Impact Classification

### CRITICAL - Major performance impact
- N+1 queries in hot paths
- Synchronous blocking in async context
- Loading unbounded data into memory

### HIGH - Significant impact
- Missing indexes on frequently queried columns
- Repeated expensive computations
- Inefficient algorithms on large datasets

### MEDIUM - Moderate impact
- Missing caching for stable data
- Suboptimal batch sizes
- Unnecessary eager loading

### LOW - Minor impact
- Micro-optimizations
- Non-hot-path inefficiencies
- Edge case performance

---

## Analysis Protocol

Execute this multi-phase analysis using the memory MCP tools available to you.

### Phase 0: Module Focus (if specified)

If a module focus was provided (e.g., "api", "reports", "sync"):

1. **Discover related entities**: Use `search_similar("$2", limit=50)` to find all code related to the module
2. **Map the module boundary**: Use `read_graph(entity="<top_match>", mode="relationships")` for key entities
3. **Scope limitation**: ALL subsequent analysis phases only consider entities discovered here

**If no module focus**: Analyze the entire codebase.

---

### Phase 1: N+1 Query Detection

1. Search for ORM loop patterns:
   - `search_similar("for loop query fetch", entityTypes=["function"])`
   - Look for attribute access on related objects inside loops
2. Identify patterns like:
   - `for order in orders: order.customer.name`
   - `[user.profile for user in users]`
3. Check for missing eager loading

---

### Phase 2: Blocking Operations in Async Context

1. Find async functions:
   - `search_similar("async await def", entityTypes=["function"])`
2. Within async functions, look for:
   - `requests.get()` instead of `aiohttp`
   - `time.sleep()` instead of `asyncio.sleep()`
   - Synchronous file I/O
   - Blocking database calls

---

### Phase 3: Missing Caching

1. Find expensive operations:
   - `search_similar("calculate compute aggregate query", entityTypes=["function"])`
2. Check if results are:
   - Stable over time (good cache candidate)
   - Called frequently with same inputs
   - Missing caching mechanism
3. Look for repeated identical queries

---

### Phase 4: Algorithm Efficiency

1. Search for nested loop patterns:
   - `search_similar("for for in range nested loop", entityTypes=["function"])`
2. Identify O(n²) or worse patterns:
   - Nested loops for searching/matching
   - Repeated list scans
   - String concatenation in loops
3. Check input size assumptions

---

### Phase 5: Memory Issues

1. Search for unbounded loading:
   - `search_similar("list all objects query all", entityTypes=["function"])`
2. Look for patterns:
   - `list(Model.objects.all())`
   - Loading entire files into memory
   - Accumulating data without limits
3. Check for iterator/generator alternatives

---

### Phase 6: Database Optimization

1. Find frequently queried fields:
   - `search_similar("filter where query by", entityTypes=["function"])`
2. Check for:
   - Queries on non-indexed columns
   - Missing composite indexes
   - Inefficient query patterns
3. Look for full table scans

---

## Issue Categories

Report findings using these categories:

### [N+1] - N+1 Query Pattern
```
[N+1] N+1 database query pattern detected
Location: orders/service.py:45
Code: for order in orders: order.user.name  # triggers query per order
Impact: O(n) queries instead of O(1)
Suggestion: Use eager loading: Order.query.options(joinedload('user'))
```

### [SYNC] - Blocking Synchronous Operation
```
[SYNC] Synchronous IO in async context
Location: api/reports.py:89
Code: requests.get(url)  # blocks event loop
Impact: Blocks all concurrent requests
Suggestion: Use aiohttp or httpx with async/await
```

### [CACHE] - Missing Caching
```
[CACHE] Expensive computation without caching
Location: analytics/reports.py:123
Code: calculate_monthly_stats()  # 5s query, called on every request
Frequency: 100+ calls/minute with identical results
Suggestion: Add caching with appropriate TTL
```

### [ALGO] - Inefficient Algorithm
```
[ALGO] O(n²) algorithm could be O(n)
Location: utils/search.py:34
Code: nested loops for finding duplicates
Input size: potentially 10k+ items
Suggestion: Use set/dict for O(n) lookup
```

### [MEMORY] - Memory Issue
```
[MEMORY] Loading entire dataset into memory
Location: export/csv.py:67
Code: data = list(Model.objects.all())  # 1M+ rows
Impact: Memory exhaustion, OOM kills
Suggestion: Use iterator/generator: Model.objects.iterator()
```

### [INDEX] - Missing Database Index
```
[INDEX] Frequent query on non-indexed column
Location: users/repository.py:89
Query: User.query.filter_by(email=email)
Column: email (no index)
Impact: Full table scan on every login
Suggestion: Add index to email column
```

### [BATCH] - Missing Batching
```
[BATCH] Individual operations that should be batched
Location: notifications/service.py:45
Code: for user in users: send_email(user)  # 1000 API calls
Impact: Rate limiting, slow execution
Suggestion: Use bulk API: send_emails(users)
```

### [EAGER] - Inefficient Loading Strategy
```
[EAGER] Eager loading unused relations
Location: api/users.py:23
Code: User.query.options(joinedload('*'))
Problem: Loading 10 relations when only 1 is needed
Suggestion: Only load relations that are actually used
```

---

## Output Format

Present your findings as:

```
## Performance Analysis

**Scope**: [Entire codebase | Focus: $2]
**Functions analyzed**: N
**Critical issues**: X
**High impact**: Y
**Medium impact**: Z

---

**Performance Issues Found:**

1. **[CRITICAL]** [N+1] Order list triggers N+1 queries
   - Location: orders/api.py:45
   - Pattern: `for order in orders: order.customer.name`
   - Impact: 100 orders = 101 queries (1 + 100)
   - Suggestion: Add `joinedload('customer')` to query

2. **[HIGH]** [SYNC] Blocking HTTP call in async handler
   - Location: api/webhooks.py:89
   - Code: `requests.post(callback_url, data)`
   - Impact: Blocks event loop for all requests
   - Suggestion: Use `httpx.AsyncClient` with await

3. **[MEDIUM]** [CACHE] Repeated expensive computation
   - Location: reports/dashboard.py:34
   - Function: `get_monthly_metrics()` (2s execution)
   - Frequency: Called 50+ times/minute
   - Suggestion: Cache with 5-minute TTL

---

Which issues would you like me to address? Enter numbers (e.g., '1,3') or 'all':
```

---

## User Delegation

After presenting findings, ask the user which issues to address.

Based on their selection, take the appropriate action:

| Issue Type | Action |
|------------|--------|
| **[N+1]** | Add eager loading or batch fetching |
| **[SYNC]** | Convert to async using appropriate library |
| **[CACHE]** | Add caching layer with appropriate TTL |
| **[ALGO]** | Refactor to more efficient algorithm |
| **[MEMORY]** | Convert to streaming/iterator approach |
| **[INDEX]** | Generate database migration for index |
| **[BATCH]** | Convert to bulk API or batch processing |
| **[EAGER]** | Remove unnecessary eager loads, add specific ones |

For each selected issue:
1. **Analyze the code** to understand the performance context
2. **Generate optimized replacement** with efficiency improvement
3. **Show the proposed fix** with performance explanation
4. **Wait for user confirmation** before making changes

Wait for user input before making any changes.
