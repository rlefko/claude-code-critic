---
description: Identify refactoring opportunities (SOLID, DRY, orphaned code, conventions)
argument-hint: [count] [feature-focus]
---

# Refactoring Analysis

You are analyzing this codebase for refactoring opportunities. Find the top $1 issues (default: 3 if not specified).

**Feature focus**: $2 (if specified, only analyze code related to this feature/area)

**Priority order**: SOLID violations > DRY violations > Orphaned code > Convention issues

## Analysis Protocol

Execute this multi-phase analysis using the memory MCP tools available to you.

### Phase 0: Feature Discovery (if feature focus specified)

If a feature focus was provided (e.g., "authentication", "payments", "user service"):

1. **Discover related entities**: Use `search_similar("$2", limit=50)` to find all code related to the feature
2. **Map the feature boundary**: Use `read_graph(entity="<top_match>", mode="relationships")` for key entities
3. **Include dependencies**: Add immediate dependencies (1 hop) to the analysis scope
4. **Scope limitation**: ALL subsequent analysis phases only consider entities discovered here

**If no feature focus**: Analyze the entire codebase.

---

### Phase 1: SOLID Principle Violations (Highest Priority)

**S - Single Responsibility Principle:**
1. Use `read_graph(mode="entities")` to find all classes
2. For large classes (many methods), use `get_implementation(name, scope="logical")` to analyze
3. Flag classes with:
   - More than 10 public methods
   - More than 400 lines of code
   - Methods handling unrelated concerns (auth + UI + database in same class)

**O - Open/Closed Principle:**
1. Search for type-switching patterns: `search_similar("switch type case", entityTypes=["function"])`
2. Look for long if-else chains checking instanceof or type properties
3. Flag code that must be modified (not extended) to add new behavior

**L - Liskov Substitution Principle:**
1. Use `read_graph(mode="relationships")` to find inheritance hierarchies
2. Look for subclasses that throw "not implemented" or override methods to do nothing
3. Check for type checks on subclass types in parent class methods

**I - Interface Segregation Principle:**
1. Find interfaces/abstract classes with many methods
2. Look for implementers that leave methods empty or throw
3. Flag "fat interfaces" that force unnecessary implementations

**D - Dependency Inversion Principle:**
1. Search for direct `new ConcreteClass()` instantiation in high-level modules
2. Look for missing dependency injection patterns
3. Flag tight coupling between modules

### Phase 2: DRY Violations (High Priority)

1. Use `search_similar` with high similarity threshold to find near-duplicate code
2. Look for functions with similar signatures across different files
3. Identify repeated patterns that could be extracted:
   - Similar validation logic
   - Repeated error handling patterns
   - Duplicate data transformation code

### Phase 3: Orphaned Code Detection (Medium Priority)

1. Use `read_graph(mode="relationships")` to analyze call graphs
2. Identify:
   - Functions with no incoming "calls" relations
   - Classes never instantiated (no incoming references)
   - Exported symbols never imported elsewhere
   - Dead code in conditionals (always true/false branches)
3. Distinguish between:
   - Entry points (CLI handlers, API routes) - NOT orphaned
   - Test utilities - NOT orphaned
   - Actually dead code - ORPHANED

### Phase 4: Convention Violations (Lower Priority)

1. Naming inconsistencies:
   - Mixed snake_case and camelCase in same codebase
   - Inconsistent prefixes/suffixes
2. File organization issues:
   - Files in wrong directories based on content
   - Overly large files that should be split
3. Code style:
   - Overly deep nesting (>4 levels)
   - Missing or inconsistent docstrings on public APIs
   - Magic numbers without named constants

## Issue Grouping

Group related issues together by:
1. **Same file** - Multiple issues in one file should be presented together
2. **Dependency chain** - If A calls B and both have issues, group them
3. **Same module/directory** - Related components with issues

## Output Format

Present your findings as a numbered list:

---

**Refactoring Opportunities Found:**

1. **[SOLID-S]** `ClassName` (path/to/file.py:1-450)
   - Problem: 15 methods handling auth, profile, and notifications
   - Impact: High - central class with 23 dependents
   - Suggestion: Split into AuthService, ProfileService, NotificationService

2. **[DRY]** Duplicate validation logic
   - `validateEmail` in src/utils/validate.py:23
   - `checkEmail` in src/forms/helpers.py:89
   - Similarity: 87%
   - Suggestion: Consolidate into single EmailValidator class

3. **[ORPHAN]** `legacy_parser` (src/parsers/legacy.py:1-200)
   - No incoming references found in codebase
   - Last modified: 6 months ago
   - Suggestion: Remove if unused, or document why it's kept

---

## User Delegation

After presenting findings, ask the user:

"Which issues would you like me to address? Enter numbers (e.g., '1,3') or 'all':"

Based on their selection:
- For **SOLID** issues: Propose the refactoring, show before/after structure
- For **DRY** issues: Extract common code, update all call sites
- For **ORPHAN** issues: Confirm deletion or add documentation
- For **Convention** issues: Apply fixes systematically

Wait for user input before making any changes.
