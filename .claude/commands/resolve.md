---
description: Find explicit debt markers (TODO, FIXME, HACK, DEPRECATED)
argument-hint: [count] [module-focus]
---

# Explicit Debt Marker Analysis

You are analyzing this codebase for **explicit technical debt markers**. Find the top $1 issues (default: 3 if not specified).

**Module focus**: $2 (if specified, only analyze code related to this module/area)

**This command is part of the tech debt diagnosis suite:**
| Command | Focus | Level |
|---------|-------|-------|
| /refactor | SOLID, DRY, orphaned code | Function/class |
| /resolve | TODO, FIXME, HACK markers | Explicit debt |
| /redocument | Coverage, usefulness, freshness | Documentation |

**Priority order**: FIXME (bugs) > HACK (fragile) > DEPRECATED (migration) > TODO (features) > TEMPORARY > XXX

---

## Explicit Debt Constitution (Core Principles)

1. **Debt acknowledged is debt trackable** - markers help prioritize
2. **Markers should age out** - old TODOs become permanent
3. **Context is required** - "TODO: fix this" is useless
4. **Link to tickets** - connects code to project management

---

## Priority Classification

### CRITICAL - Acknowledged bugs
- FIXME markers indicating known bugs
- HACK markers in security-critical code
- DEBT markers affecting data integrity

### HIGH - Technical risk
- HACK/workaround in production paths
- DEPRECATED code still heavily used
- Old TODOs in critical systems

### MEDIUM - Missing features
- TODO for planned functionality
- TEMPORARY code that became permanent
- Version-specific workarounds for old versions

### LOW - Nice to have
- XXX/NOTE markers for review
- Minor TODOs in non-critical code
- Style/cleanup TODOs

---

## Analysis Protocol

Execute this multi-phase analysis using the memory MCP tools available to you.

### Phase 0: Module Focus (if specified)

If a module focus was provided (e.g., "auth", "payments", "api"):

1. **Discover related entities**: Use `search_similar("$2", limit=50)` to find all code related to the module
2. **Map the module boundary**: Use `read_graph(entity="<top_match>", mode="relationships")` for key entities
3. **Scope limitation**: ALL subsequent analysis phases only consider entities discovered here

**If no module focus**: Analyze the entire codebase.

---

### Phase 1: TODO Detection

1. Search for TODO markers:
   - `search_similar("TODO todo", entityTypes=["function", "class"])`
2. For each TODO, evaluate:
   - Age (if determinable from git)
   - Context/explanation quality
   - Ticket reference presence
   - Code criticality
3. Prioritize by risk and age

---

### Phase 2: FIXME Detection

1. Search for FIXME markers:
   - `search_similar("FIXME fixme bug", entityTypes=["function", "class"])`
2. These are acknowledged bugs - highest priority
3. Check for:
   - Bug severity
   - User impact
   - Time since acknowledgment

---

### Phase 3: HACK Detection

1. Search for HACK/workaround markers:
   - `search_similar("HACK hack workaround kludge", entityTypes=["function", "class"])`
2. Evaluate fragility:
   - What would break the hack?
   - Is there a proper solution documented?
   - Is it in a critical path?

---

### Phase 4: DEPRECATED Detection

1. Search for deprecated markers:
   - `search_similar("deprecated Deprecated DEPRECATED", entityTypes=["function", "class"])`
2. Check usage:
   - How many call sites?
   - Is replacement documented?
   - Migration progress

---

### Phase 5: TEMPORARY/XXX Detection

1. Search for temporary markers:
   - `search_similar("TEMPORARY temporary XXX NOTE", entityTypes=["function", "class"])`
2. Check for:
   - "Temporary" code that's been there >6 months
   - XXX markers indicating needed review
   - NOTE markers with actionable content

---

### Phase 6: DEBT Marker Detection

1. Search for explicit debt markers:
   - `search_similar("TECH DEBT tech debt technical debt", entityTypes=["function", "class"])`
2. These are explicitly acknowledged debt
3. Evaluate scope and priority

---

## Issue Categories

Report findings using these categories:

### [TODO] - TODO Comments
```
[TODO] Unresolved TODO comment
Location: auth/service.py:45
Comment: # TODO: implement proper rate limiting
Age: 8 months
Priority: HIGH (security-related)
Suggestion: Create ticket, implement, or remove if not needed
```

### [FIXME] - FIXME Comments
```
[FIXME] Known bug marked for fixing
Location: orders/calculator.py:89
Comment: # FIXME: rounding error on large orders
Age: 3 months
Impact: Financial calculations affected
Suggestion: Fix the bug or document as known limitation
```

### [HACK] - HACK/Workaround Comments
```
[HACK] Workaround that should be proper fix
Location: integrations/legacy.py:34
Comment: # HACK: Legacy API returns wrong format
Age: 1 year
Risk: Brittle, may break on API changes
Suggestion: Fix properly or document why hack is necessary
```

### [DEPRECATED] - Deprecated Without Replacement
```
[DEPRECATED] Deprecated code still in use
Location: utils/helpers.py:23
Marker: @deprecated / @Deprecated
Usage: 15 call sites
Problem: No migration path provided
Suggestion: Document replacement, migrate callers, then remove
```

### [TEMPORARY] - Temporary Code
```
[TEMPORARY] Code marked as temporary
Location: features/beta.py:67
Comment: # Temporary until new API is ready
Age: 6 months
Risk: Temporary became permanent
Suggestion: Complete migration or document permanent status
```

### [VERSION] - Version-Specific Workaround
```
[VERSION] Version-specific workaround
Location: compat/python.py:12
Comment: # Workaround for Python 3.8 bug
Current: Python 3.11+
Status: Workaround no longer needed
Suggestion: Remove workaround, simplify code
```

### [DEBT] - Explicit Tech Debt Marker
```
[DEBT] Explicit technical debt marker
Location: services/reports.py:156
Comment: # TECH DEBT: This entire module needs refactoring
Age: 1.5 years
Scope: 800 lines, 25 functions
Suggestion: Break into prioritized tasks, create tickets
```

### [XXX] - XXX/NOTE Requiring Attention
```
[XXX] Attention marker requiring review
Location: security/auth.py:34
Comment: # XXX: Is this secure enough?
Type: Security concern
Suggestion: Review, document conclusion, or fix
```

---

## Output Format

Present your findings as:

```
## Explicit Debt Analysis

**Scope**: [Entire codebase | Focus: $2]
**Files analyzed**: N
**Total markers found**: X

**By Type:**
| Type | Count | Critical | High | Medium | Low |
|------|-------|----------|------|--------|-----|
| TODO | 45 | 2 | 8 | 20 | 15 |
| FIXME | 8 | 5 | 3 | 0 | 0 |
| HACK | 12 | 3 | 5 | 4 | 0 |
| ... | ... | ... | ... | ... | ... |

---

**Most Critical Debt Markers:**

1. **[CRITICAL]** [FIXME] Rounding error in payment calculation
   - Location: payments/calculator.py:89
   - Comment: `# FIXME: loses cents on large orders`
   - Age: 6 months
   - Impact: Financial loss on high-value orders
   - Suggestion: Fix decimal handling, add tests

2. **[HIGH]** [HACK] Fragile API workaround
   - Location: integrations/shipping.py:45
   - Comment: `# HACK: API sometimes returns null for tracking`
   - Age: 1 year
   - Risk: Breaks when API behavior changes
   - Suggestion: Add proper null handling, contact API vendor

3. **[MEDIUM]** [TODO] Missing rate limiting
   - Location: api/public.py:23
   - Comment: `# TODO: add rate limiting before launch`
   - Age: 4 months
   - Status: Launched without rate limiting
   - Suggestion: Implement rate limiting urgently

---

Which issues would you like me to address? Enter numbers (e.g., '1,3') or 'all':
```

---

## User Delegation

After presenting findings, ask the user which issues to address.

Based on their selection, take the appropriate action:

| Issue Type | Action |
|------------|--------|
| **[TODO]** | Implement the feature or create ticket and update comment |
| **[FIXME]** | Fix the bug, add tests |
| **[HACK]** | Implement proper solution or document why hack is permanent |
| **[DEPRECATED]** | Document replacement, start migration |
| **[TEMPORARY]** | Complete migration or formalize as permanent |
| **[VERSION]** | Remove workaround if version requirement no longer applies |
| **[DEBT]** | Break into smaller tasks, create tickets |
| **[XXX]** | Review concern, document conclusion or fix |

For each selected issue:
1. **Analyze the context** to understand what's needed
2. **Generate appropriate solution** or updated documentation
3. **Show the proposed change** with explanation
4. **Wait for user confirmation** before making changes

Wait for user input before making any changes.
