---
description: Diagnose type safety issues (annotations, strictness, inference)
argument-hint: [count] [module-focus]
---

# Type Safety Debt Analysis

You are analyzing this codebase for **type safety issues**. Find the top $1 issues (default: 3 if not specified).

**Module focus**: $2 (if specified, only analyze code related to this module/area)

**This command is part of the tech debt diagnosis suite:**
| Command | Focus | Level |
|---------|-------|-------|
| /refactor | SOLID, DRY, orphaned code | Function/class |
| /retype | Annotations, strictness, inference | Type safety |
| /redocument | Coverage, usefulness, freshness | Documentation |

**Priority order**: Public API untyped > Any overuse > Unsafe casts > Inconsistent types > Nullable mishandling > Complex inference

---

## Type Safety Constitution (Core Principles)

1. **Types catch bugs at compile time** - better than runtime errors
2. **Public APIs must be typed** - callers need to know contracts
3. **Avoid Any** - it defeats the purpose of typing
4. **Be explicit about nullability** - None is a common bug source

---

## Tier Classification

### Tier A - FAIL if untyped
Public interfaces requiring full type annotations:
- Public function parameters and returns
- Public class attributes
- Exported module members
- API request/response types

### Tier B - WARN if untyped
Internal code that benefits from types:
- Shared utility functions
- Data transformation functions
- Configuration structures
- Database models

### Tier C - INFO only
Low-priority typing:
- Local helper functions
- Simple lambda expressions
- Test utilities

### Complexity Escalation
These bump requirements up a tier:
- Functions with >3 parameters
- Generic/parameterized types
- Union types or overloads
- Async functions

---

## Analysis Protocol

Execute this multi-phase analysis using the memory MCP tools available to you.

### Phase 0: Module Focus (if specified)

If a module focus was provided (e.g., "api", "models", "utils"):

1. **Discover related entities**: Use `search_similar("$2", limit=50)` to find all code related to the module
2. **Map the module boundary**: Use `read_graph(entity="<top_match>", mode="relationships")` for key entities
3. **Scope limitation**: ALL subsequent analysis phases only consider entities discovered here

**If no module focus**: Analyze the entire codebase.

---

### Phase 1: Missing Type Annotation Detection

1. Find public functions:
   - `search_similar("def function export public", entityTypes=["function"])`
2. Use `get_implementation(name, scope="logical")` to check signatures
3. Flag functions missing:
   - Parameter type hints
   - Return type hints
   - Class attribute types

---

### Phase 2: Any/Unknown Overuse Detection

1. Search for Any usage:
   - `search_similar("Any unknown any object", entityTypes=["function"])`
2. Flag patterns:
   - `def func(data: Any) -> Any`
   - `Dict[str, Any]` where structure is known
   - `List[Any]` where element type is known
3. Check if specific types could replace Any

---

### Phase 3: Unsafe Cast Detection

1. Search for type assertions:
   - `search_similar("cast as type assert", entityTypes=["function"])`
2. Flag patterns:
   - `data as User` without validation
   - `cast(User, data)` without checks
   - `# type: ignore` without explanation
3. Check for runtime validation

---

### Phase 4: Type Inconsistency Detection

1. Find common types used across files:
   - `search_similar("user_id order_id config", entityTypes=["function"])`
2. Check for inconsistencies:
   - Same concept with different types (`user_id: int` vs `user_id: str`)
   - Different nullability for same field
   - Conflicting union types
3. Flag inconsistent typing

---

### Phase 5: Nullable Mishandling Detection

1. Search for Optional types:
   - `search_similar("Optional None null undefined", entityTypes=["function"])`
2. Check for unsafe access:
   - `user.profile.name` where `profile` might be None
   - Missing null checks before attribute access
   - Implicit None returns
3. Flag potential None errors

---

### Phase 6: Complex Inference Issues

1. Find complex expressions:
   - `search_similar("map filter reduce chain", entityTypes=["function"])`
2. Flag expressions where:
   - Type is not obvious from context
   - Long method chains lose type info
   - Generic type parameters are inferred incorrectly
3. Suggest explicit type annotations

---

## Issue Categories

Report findings using these categories:

### [UNTYPED] - Missing Type Annotations
```
[UNTYPED] Public function lacks type annotations
Symbol: calculate_total(items, discount, tax) in orders/pricing.py:23
Tier: A (public API)
Problem: Caller doesn't know expected types
Suggestion: def calculate_total(items: list[Item], discount: float, tax: float) -> Decimal:
```

### [ANY] - Overuse of Any/unknown
```
[ANY] Any type used where specific type possible
Location: utils/parser.py:45
Code: def parse(data: Any) -> Any:
Problem: No type checking, documentation, or IDE support
Suggestion: Define specific types or use generics
```

### [ASSERT] - Unsafe Type Assertion
```
[ASSERT] Type assertion without runtime validation
Location: api/handlers.py:67
Code: user = data as User  # or cast(User, data)
Risk: Runtime type mismatch causes subtle bugs
Suggestion: Validate structure matches expected type
```

### [GENERIC] - Overly Generic Types
```
[GENERIC] Dict/Object where structured type appropriate
Location: config/settings.py:23
Type: config: dict[str, Any]
Problem: No validation, IDE support, or documentation
Suggestion: Define Config dataclass/TypedDict with specific fields
```

### [INCONSISTENT] - Inconsistent Typing
```
[INCONSISTENT] Same concept typed differently
Locations: user_id: int (models.py), user_id: str (api.py)
Problem: Type confusion leads to bugs
Suggestion: Create UserId type alias, use consistently
```

### [NULLABLE] - Missing Null Handling
```
[NULLABLE] Nullable value used without check
Location: orders/service.py:89
Code: order.user.email  # user can be None
Risk: NoneType has no attribute 'email'
Suggestion: Add null check or use Optional[] with handling
```

### [CAST] - Unsafe Cast
```
[CAST] Casting without validation
Location: serializers/json.py:34
Code: return int(value)  # value might not be numeric
Risk: ValueError at runtime
Suggestion: Validate before casting or use try/except
```

### [INFERENCE] - Complex Inference
```
[INFERENCE] Complex expression type not explicit
Location: utils/transform.py:67
Code: result = complex_chain().map(fn).filter(pred).reduce(acc)
Problem: Type is unclear, hard to debug
Suggestion: Add explicit type annotation for complex expressions
```

---

## Output Format

Present your findings as:

```
## Type Safety Analysis

**Scope**: [Entire codebase | Focus: $2]
**Functions analyzed**: N
**Tier A coverage**: X% (Y/Z typed)
**Tier B coverage**: X% (Y/Z typed)

---

**Type Safety Issues Found:**

1. **[UNTYPED]** `process_order()` - Public function untyped
   - Location: orders/service.py:45
   - Tier: A (public API, complex logic)
   - Parameters: 5 untyped parameters
   - Suggestion: Add full type annotations

2. **[ANY]** `parse_config()` - Excessive Any usage
   - Location: config/loader.py:23
   - Current: `def parse_config(data: Any) -> Any`
   - Problem: Loses all type safety
   - Suggestion: Define `ConfigData` TypedDict

3. **[NULLABLE]** `get_user_profile()` - Unsafe null access
   - Location: users/service.py:89
   - Code: `return user.profile.avatar_url`
   - Risk: `profile` can be None
   - Suggestion: Add null check or use optional chaining

---

Which issues would you like me to address? Enter numbers (e.g., '1,3') or 'all':
```

---

## User Delegation

After presenting findings, ask the user which issues to address.

Based on their selection, take the appropriate action:

| Issue Type | Action |
|------------|--------|
| **[UNTYPED]** | Add type annotations based on code analysis |
| **[ANY]** | Replace with specific types or generics |
| **[ASSERT]** | Add runtime validation before assertion |
| **[GENERIC]** | Define TypedDict/dataclass for structure |
| **[INCONSISTENT]** | Create type alias and apply consistently |
| **[NULLABLE]** | Add null checks or optional handling |
| **[CAST]** | Add validation before type conversion |
| **[INFERENCE]** | Add explicit type annotation |

For each selected issue:
1. **Analyze the code** to infer correct types
2. **Generate type annotations** following project conventions
3. **Show the proposed types** with explanation
4. **Wait for user confirmation** before making changes

Wait for user input before making any changes.
