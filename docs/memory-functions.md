# Memory Functions Reference

> MCP tools for semantic code memory in Claude Code

This document provides a complete reference for all MCP memory tools available to Claude Code when working with your codebase.

---

## Table of Contents

1. [Overview](#overview)
2. [Search Functions](#search-functions)
3. [Graph Functions](#graph-functions)
4. [Entity Management](#entity-management)
5. [Relation Management](#relation-management)
6. [Best Practices](#best-practices)

---

## Overview

Claude Code Memory provides semantic search and knowledge graph capabilities through MCP (Model Context Protocol) tools. These tools allow Claude to:

- **Search** your codebase semantically (by meaning, not just keywords)
- **Navigate** code relationships and dependencies
- **Store** learned patterns and insights
- **Recall** past implementations and solutions

### Tool Naming Convention

All memory tools use the MCP prefix format:

```
mcp__<collection-name>-memory__<tool-name>
```

Example: `mcp__my-project-memory__search_similar`

### Chunk Types

The memory system uses two chunk types for progressive disclosure:

| Chunk Type | Content | Speed | Use Case |
|------------|---------|-------|----------|
| `metadata` | Function signatures, class definitions, file info | Fast (3-5ms) | Initial search, overview |
| `implementation` | Full source code, docstrings | Slower (50-200ms) | Deep dive, detailed analysis |

---

## Search Functions

### search_similar

The primary search function for finding relevant code and knowledge.

**Syntax**:
```python
search_similar(
    query: str,
    limit: int = 20,
    entityTypes: List[str] = None,
    searchMode: str = "hybrid"
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Natural language search query |
| `limit` | int | 20 | Maximum results to return |
| `entityTypes` | list | all | Filter by entity or chunk types |
| `searchMode` | string | "hybrid" | Search algorithm to use |

**Entity Types** (filter results):

```python
# Code entities
entityTypes=["function"]        # Functions and methods
entityTypes=["class"]           # Classes and components
entityTypes=["file"]            # File-level metadata
entityTypes=["documentation"]   # Docstrings and comments
entityTypes=["text_chunk"]      # Free-form text content
entityTypes=["relation"]        # Code relationships

# Chunk types (progressive disclosure)
entityTypes=["metadata"]        # Fast: signatures only
entityTypes=["implementation"]  # Full: complete source code

# Combined (OR logic)
entityTypes=["function", "class", "metadata"]
```

**Search Modes**:

| Mode | Algorithm | Best For |
|------|-----------|----------|
| `hybrid` | 70% semantic + 30% BM25 | General queries (default) |
| `semantic` | Embedding similarity only | Conceptual queries |
| `keyword` | BM25 term matching | Exact names, identifiers |

**Examples**:

```python
# Fast overview search (metadata only)
search_similar("authentication logic", entityTypes=["metadata"])

# Find specific function implementations
search_similar("validate_user_token", searchMode="keyword", entityTypes=["function"])

# Conceptual search for patterns
search_similar("error handling patterns", searchMode="semantic", entityTypes=["implementation_pattern"])

# Find classes related to a concept
search_similar("user management", entityTypes=["class", "metadata"], limit=10)

# Search for debugging patterns
search_similar("connection refused", entityTypes=["debugging_pattern"])
```

**Returns**: List of matching entities with similarity scores, sorted by relevance.

---

## Graph Functions

### read_graph

Explore code relationships and dependencies.

**Syntax**:
```python
read_graph(
    entity: str = None,
    mode: str = "smart"
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity` | string | None | Focus on specific entity (optional) |
| `mode` | string | "smart" | Graph traversal mode |

**Modes**:

| Mode | Output | Best For |
|------|--------|----------|
| `smart` | AI-generated summary with stats | Quick understanding |
| `entities` | List of connected entities | Finding related code |
| `relationships` | All relations (incoming/outgoing) | Dependency analysis |
| `raw` | Complete graph data | Detailed inspection |

**Examples**:

```python
# Get AI summary of a component
read_graph(entity="AuthService", mode="smart")
# Returns: "AuthService has 12 methods, depends on TokenValidator, UserRepository..."

# Find what depends on a function
read_graph(entity="validate_token", mode="relationships")
# Returns: All callers and callees

# List all entities connected to a module
read_graph(entity="auth_module", mode="entities")
# Returns: Functions, classes, files in the module

# Get full graph data for analysis
read_graph(entity="DatabaseManager", mode="raw")
# Returns: Complete entity and relation data
```

### get_implementation

Retrieve source code for specific entities.

**Syntax**:
```python
get_implementation(
    entity: str,
    scope: str = "logical"
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity` | string | required | Entity name to retrieve |
| `scope` | string | "logical" | How much context to include |

**Scopes**:

| Scope | Returns | Use Case |
|-------|---------|----------|
| `exact` | Only the specified entity | Quick lookup |
| `logical` | Entity + helper functions | Understanding implementation |
| `dependencies` | Entity + all dependencies | Full context |

**Examples**:

```python
# Get just the function
get_implementation("process_payment", scope="exact")

# Get function with helpers it calls
get_implementation("process_payment", scope="logical")

# Get full dependency chain
get_implementation("process_payment", scope="dependencies")
```

---

## Entity Management

### create_entities

Add new knowledge to the memory system.

**Syntax**:
```python
create_entities(
    entities: List[dict]
)
```

**Entity Structure**:

```python
{
    "name": "EntityName",
    "entityType": "category",
    "observations": ["observation 1", "observation 2"]
}
```

**Entity Types for Manual Entries**:

| Type | Target % | Description |
|------|----------|-------------|
| `debugging_pattern` | 30% | Investigation techniques, system analysis |
| `implementation_pattern` | 25% | Code patterns, best practices |
| `integration_pattern` | 15% | APIs, databases, third-party services |
| `configuration_pattern` | 12% | Environment setup, deployment |
| `architecture_pattern` | 10% | System design, component structure |
| `performance_pattern` | 8% | Optimization, caching |
| `knowledge_insight` | - | Research findings, lessons learned |
| `active_issue` | - | Current tasks, user-reported issues |
| `ideas` | - | Feature suggestions, future work |

**Examples**:

```python
# Store a debugging pattern
create_entities([{
    "name": "AuthTokenExpiredDebug",
    "entityType": "debugging_pattern",
    "observations": [
        "Check token expiration with jwt.decode()",
        "Verify clock sync between services",
        "Check refresh token rotation logic"
    ]
}])

# Store an implementation pattern
create_entities([{
    "name": "RetryWithBackoff",
    "entityType": "implementation_pattern",
    "observations": [
        "Use exponential backoff: delay * 2^attempt",
        "Set max retries to 3-5",
        "Add jitter to prevent thundering herd"
    ]
}])

# Store an active issue
create_entities([{
    "name": "MemoryLeakInWatcher",
    "entityType": "active_issue",
    "observations": [
        "File watcher accumulates references",
        "Occurs after 1000+ file changes",
        "Likely in event listener cleanup"
    ]
}])
```

### add_observations

Update existing entities with new information.

**Syntax**:
```python
add_observations(
    observations: List[dict]
)
```

**Examples**:

```python
# Add new observations to existing entity
add_observations([{
    "entityName": "AuthService",
    "contents": [
        "Now supports OAuth2 flow",
        "Added rate limiting (100 req/min)"
    ]
}])

# Update debugging pattern with solution
add_observations([{
    "entityName": "AuthTokenExpiredDebug",
    "contents": [
        "SOLUTION: Token was being cached without expiry check",
        "Fix: Add cache TTL matching token expiry"
    ]
}])
```

### delete_entities

Remove entities from the memory system.

**Syntax**:
```python
delete_entities(
    entityNames: List[str]
)
```

**Examples**:

```python
# Remove resolved issue
delete_entities(["MemoryLeakInWatcher"])

# Remove outdated pattern
delete_entities(["OldAuthPattern", "DeprecatedAPIUsage"])
```

---

## Relation Management

### create_relations

Define relationships between entities.

**Syntax**:
```python
create_relations(
    relations: List[dict]
)
```

**Relation Structure**:

```python
{
    "from": "SourceEntity",
    "to": "TargetEntity",
    "relationType": "relationship_type"
}
```

**Common Relation Types**:

| Type | Meaning |
|------|---------|
| `calls` | Function calls another function |
| `imports` | File imports another file |
| `extends` | Class extends another class |
| `implements` | Class implements interface |
| `uses` | Entity uses another entity |
| `contains` | Module contains class/function |
| `depends_on` | General dependency |

**Examples**:

```python
# Define function call relationship
create_relations([{
    "from": "AuthService.login",
    "to": "TokenValidator.validate",
    "relationType": "calls"
}])

# Define module structure
create_relations([
    {"from": "auth_module", "to": "AuthService", "relationType": "contains"},
    {"from": "auth_module", "to": "TokenValidator", "relationType": "contains"}
])

# Define pattern usage
create_relations([{
    "from": "PaymentProcessor",
    "to": "RetryWithBackoff",
    "relationType": "uses"
}])
```

### delete_relations

Remove relationships between entities.

**Syntax**:
```python
delete_relations(
    relations: List[dict]
)
```

**Examples**:

```python
# Remove outdated relationship
delete_relations([{
    "from": "OldService",
    "to": "DeprecatedAPI",
    "relationType": "calls"
}])
```

---

## Best Practices

### Memory-First Debugging

Always search memory before diving into code:

```python
# Phase 1: Fast discovery
search_similar("authentication error", entityTypes=["metadata", "debugging_pattern"])

# Phase 2: Find similar past issues
search_similar("token validation failed", entityTypes=["debugging_pattern"])

# Phase 3: Understand affected code
read_graph(entity="AuthService", mode="smart")
get_implementation("validate_token", scope="logical")
```

### Storing Patterns

Document successful solutions:

```python
# After solving a problem, store the pattern
create_entities([{
    "name": "CORSConfigurationFix",
    "entityType": "debugging_pattern",
    "observations": [
        "Symptom: 'Access-Control-Allow-Origin' error in browser",
        "Cause: Missing CORS middleware configuration",
        "Solution: Add cors() middleware before routes",
        "File: src/server.ts:15"
    ]
}])
```

### Performance Tips

1. **Start with metadata searches** - 90% faster than full searches:
   ```python
   search_similar("user service", entityTypes=["metadata"])
   ```

2. **Use keyword mode for exact names**:
   ```python
   search_similar("processPayment", searchMode="keyword")
   ```

3. **Filter by entity type** to reduce noise:
   ```python
   search_similar("validation", entityTypes=["function", "class"])
   ```

4. **Use progressive disclosure** - get metadata first, then implementation:
   ```python
   # Step 1: Fast overview
   results = search_similar("auth", entityTypes=["metadata"], limit=10)

   # Step 2: Deep dive on specific entity
   get_implementation("AuthService.login", scope="logical")
   ```

### Memory Hygiene

Keep memory clean and useful:

1. **Delete resolved issues**:
   ```python
   delete_entities(["FixedBug123"])
   ```

2. **Update outdated patterns**:
   ```python
   add_observations([{
       "entityName": "APIPattern",
       "contents": ["Updated: Now uses v2 endpoints"]
   }])
   ```

3. **Use descriptive names**:
   ```python
   # Good: Descriptive and searchable
   "name": "JWTTokenRefreshPattern"

   # Bad: Generic and forgettable
   "name": "TokenFix1"
   ```

### Category Selection Guide

Choose the right entity type:

| If the knowledge is about... | Use |
|------------------------------|-----|
| How to investigate a bug | `debugging_pattern` |
| How to implement a feature | `implementation_pattern` |
| How to connect to external service | `integration_pattern` |
| How to configure/deploy | `configuration_pattern` |
| System design decisions | `architecture_pattern` |
| Making things faster | `performance_pattern` |
| Research or experiments | `knowledge_insight` |
| Current work in progress | `active_issue` |
| Future possibilities | `ideas` |

---

## Quick Reference

### Search Patterns

```python
# Fast metadata search
search_similar("query", entityTypes=["metadata"])

# Find functions by name
search_similar("functionName", searchMode="keyword", entityTypes=["function"])

# Conceptual search
search_similar("how to handle errors", searchMode="semantic")

# Find debugging solutions
search_similar("error message", entityTypes=["debugging_pattern"])
```

### Graph Patterns

```python
# Quick overview
read_graph(entity="ComponentName", mode="smart")

# Find dependencies
read_graph(entity="ComponentName", mode="relationships")

# Get source code
get_implementation("function_name", scope="logical")
```

### Storage Patterns

```python
# Store new pattern
create_entities([{"name": "...", "entityType": "...", "observations": [...]}])

# Update existing
add_observations([{"entityName": "...", "contents": [...]}])

# Clean up
delete_entities(["..."])
```

---

## Related Documentation

- [CLI Reference](CLI_REFERENCE.md) - Command-line interface
- [CLAUDE.md](../CLAUDE.md) - Memory workflow examples
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues
- [Configuration](CONFIGURATION.md) - Settings reference
