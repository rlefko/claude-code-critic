# CLI Reference

> **claude-indexer** - Universal semantic indexing for codebases

The `claude-indexer` command-line interface provides tools for indexing, searching, and managing semantic code memory.

---

## Installation

```bash
# Install global wrapper
./install.sh

# Verify installation
claude-indexer --version
```

---

## Commands Overview

| Command | Description |
|---------|-------------|
| `index` | Index an entire project or specific files |
| `search` | Search across entities, relations, and chats |
| `file` | Index a single file |
| `watch` | Real-time file monitoring |
| `service` | Background service management |
| `hooks` | Git hooks management |
| `add-mcp` | Configure MCP server |
| `chat` | Chat history indexing |
| `init` | Initialize project configuration |
| `show-config` | Display effective configuration |

---

## index

Index an entire project or specific files from stdin.

```bash
claude-indexer index -p PATH -c COLLECTION [OPTIONS]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-p, --project PATH` | Project directory path | **Required** |
| `-c, --collection TEXT` | Collection name for vector storage | **Required** |
| `-v, --verbose` | Enable verbose output | Off |
| `-q, --quiet` | Suppress non-error output | Off |
| `--include-tests` | Include test files in indexing | Off |
| `--clear` | Clear code-indexed memories (preserves manual) | Off |
| `--clear-all` | Clear ALL memories (including manual) | Off |
| `--depth [basic\|full]` | Analysis depth | full |
| `--files-from-stdin` | Read file paths from stdin (batch mode) | Off |
| `--since COMMIT` | Index changes since git commit/ref (e.g., HEAD~5) | Off |
| `--staged` | Index only staged files (for pre-commit hooks) | Off |
| `--pr-diff BRANCH` | Index changes for PR against base branch | Off |
| `--config PATH` | Configuration file path | Auto-detect |

### Examples

```bash
# Index current directory
claude-indexer index -p . -c my-project

# Index with verbose output
claude-indexer index -p . -c my-project --verbose

# Clear and reindex (preserves manual memories)
claude-indexer index -p . -c my-project --clear

# Include test files
claude-indexer index -p . -c my-project --include-tests

# Batch index from file list (4-15x faster)
echo "src/auth.py
src/api/users.py
src/utils.py" | claude-indexer index -p . -c my-project --files-from-stdin

# Git-aware incremental indexing (v2.9.1+)
claude-indexer index -p . -c my-project --since HEAD~5

# Index only staged files (pre-commit)
claude-indexer index -p . -c my-project --staged

# Index PR changes against main branch
claude-indexer index -p . -c my-project --pr-diff main
```

### Git-Aware Incremental Indexing (v2.9.1+)

The `--since`, `--staged`, and `--pr-diff` options enable git-aware change detection:

| Option | Use Case | Description |
|--------|----------|-------------|
| `--since COMMIT` | Regular development | Index changes since a specific commit |
| `--staged` | Pre-commit hooks | Index only staged files |
| `--pr-diff BRANCH` | CI/PR workflows | Index changes in current branch vs base |

**Features:**
- Automatic rename detection (updates paths in place, preserves history)
- Deletion handling (removes entities for deleted files)
- Falls back to hash-based detection for non-git repos
- Tracks `_last_indexed_commit` in state file for automatic incremental mode

### Batch Indexing (v2.8+)

The `--files-from-stdin` flag enables batch processing for significant performance improvements:

| Files | Sequential | Batch | Speedup |
|-------|------------|-------|---------|
| 5 | 15s | 4s | 4x |
| 10 | 30s | 5s | 6x |
| 50 | 150s | 10s | 15x |

---

## search

Search across code entities, relations, and chat conversations.

```bash
claude-indexer search QUERY -p PATH -c COLLECTION [OPTIONS]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-p, --project PATH` | Project directory path | **Required** |
| `-c, --collection TEXT` | Collection name | **Required** |
| `--limit INTEGER` | Maximum results | 10 |
| `--type [entity\|relation\|chat\|all]` | Filter by result type | all |
| `--mode [hybrid\|semantic\|keyword]` | Search mode | hybrid |
| `-v, --verbose` | Enable verbose output | Off |
| `-q, --quiet` | Suppress non-error output | Off |

### Search Modes

| Mode | Description | Best For |
|------|-------------|----------|
| `hybrid` | Semantic + BM25 keyword (70/30) | General queries |
| `semantic` | Vector similarity only | Conceptual searches |
| `keyword` | BM25 exact term matching | Specific identifiers |

### Examples

```bash
# Basic search
claude-indexer search "authentication" -p . -c my-project

# Search with limit
claude-indexer search "user validation" -p . -c my-project --limit 20

# Keyword-only search (BM25)
claude-indexer search "getUserById" -p . -c my-project --mode keyword

# Semantic-only search
claude-indexer search "login error handling" -p . -c my-project --mode semantic

# Filter by type
claude-indexer search "auth" -p . -c my-project --type entity
```

---

## file

Index a single file.

```bash
claude-indexer file FILE_PATH -p PATH -c COLLECTION [OPTIONS]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-p, --project PATH` | Project directory path | **Required** |
| `-c, --collection TEXT` | Collection name | **Required** |
| `-v, --verbose` | Enable verbose output | Off |
| `-q, --quiet` | Suppress non-error output | Off |

### Examples

```bash
# Index single file
claude-indexer file ./src/auth.py -p . -c my-project

# Quiet mode (for hooks)
claude-indexer file ./src/auth.py -p . -c my-project --quiet
```

---

## watch

Real-time file monitoring for automatic indexing.

```bash
claude-indexer watch start -p PATH -c COLLECTION [OPTIONS]
```

### Subcommands

| Command | Description |
|---------|-------------|
| `start` | Start file watching |

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-p, --project PATH` | Project directory path | **Required** |
| `-c, --collection TEXT` | Collection name | **Required** |
| `-v, --verbose` | Enable verbose output | Off |

### Examples

```bash
# Start watching current directory
claude-indexer watch start -p . -c my-project

# Watch with verbose logging
claude-indexer watch start -p . -c my-project --verbose
```

---

## service

Background service for multi-project indexing.

```bash
claude-indexer service COMMAND [OPTIONS]
```

### Subcommands

| Command | Description |
|---------|-------------|
| `start` | Start the background service |
| `status` | Show service status |
| `add-project` | Add a project to watch list |

### Examples

```bash
# Start background service
claude-indexer service start

# Check service status
claude-indexer service status

# Add project to service
claude-indexer service add-project /path/to/project my-project

# Add with verbose
claude-indexer service add-project /path/to/project my-project --verbose
```

---

## hooks

Git hooks management.

```bash
claude-indexer hooks COMMAND -p PATH -c COLLECTION [OPTIONS]
```

### Subcommands

| Command | Description |
|---------|-------------|
| `install` | Install git hooks |
| `status` | Check hook status |
| `uninstall` | Remove git hooks |

### Examples

```bash
# Install hooks
claude-indexer hooks install -p . -c my-project

# Check status
claude-indexer hooks status -p . -c my-project

# Remove hooks
claude-indexer hooks uninstall -p . -c my-project
```

### Installed Hooks

| Hook | Trigger | Action |
|------|---------|--------|
| pre-commit | Before commit | Batch index staged files |
| post-merge | After merge/pull | Index changed files |
| post-checkout | After branch switch | Index changed files |

---

## add-mcp

Configure MCP server for a collection.

```bash
claude-indexer add-mcp -c COLLECTION [OPTIONS]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-c, --collection TEXT` | Collection name | **Required** |
| `-p, --project PATH` | Project directory | Current dir |

### Examples

```bash
# Add MCP configuration
claude-indexer add-mcp -c my-project

# Specify project path
claude-indexer add-mcp -c my-project -p /path/to/project
```

### Generated Configuration

Creates `.mcp.json` in the project root:

```json
{
  "mcpServers": {
    "my-project-memory": {
      "command": "node",
      "args": ["/path/to/mcp-qdrant-memory/dist/index.js"],
      "env": {
        "QDRANT_URL": "http://localhost:6333",
        "QDRANT_COLLECTION_NAME": "my-project"
      }
    }
  }
}
```

---

## chat

Chat history indexing and summarization.

```bash
claude-indexer chat COMMAND -p PATH -c COLLECTION [OPTIONS]
```

### Subcommands

| Command | Description |
|---------|-------------|
| `index` | Process and index chat history |
| `search` | Search chat insights |
| `html-report` | Generate HTML report |

### Examples

```bash
# Index chat history
claude-indexer chat index -p . -c my-project --limit 50

# Search chat insights
claude-indexer chat search "debugging patterns" -p . -c my-project

# Generate report
claude-indexer chat html-report -p . -c my-project
```

---

## init

Initialize project configuration.

```bash
claude-indexer init -p PATH [OPTIONS]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-p, --project PATH` | Project directory | **Required** |
| `-c, --collection TEXT` | Collection name | Auto from path |

### Examples

```bash
# Initialize project
claude-indexer init -p .

# With custom collection name
claude-indexer init -p . -c custom-name
```

---

## show-config

Display effective configuration for a project.

```bash
claude-indexer show-config -p PATH [OPTIONS]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-p, --project PATH` | Project directory | **Required** |
| `-v, --verbose` | Show all config sources | Off |

### Examples

```bash
# Show config
claude-indexer show-config -p .

# Verbose with sources
claude-indexer show-config -p . --verbose
```

---

## Global Options

These options are available for most commands:

| Flag | Description |
|------|-------------|
| `-v, --verbose` | Enable detailed output |
| `-q, --quiet` | Suppress non-error output |
| `--config PATH` | Custom configuration file |
| `--help` | Show command help |
| `--version` | Show version |

---

## Configuration

### settings.txt

Global configuration in the Claude Code Memory directory:

```ini
# Embedding configuration
VOYAGE_API_KEY=your-key-here
EMBEDDING_PROVIDER=voyage
EMBEDDING_MODEL=voyage-3-lite

# Qdrant configuration
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=optional-api-key

# OpenAI (for chat analysis)
OPENAI_API_KEY=your-key-here
```

### .claudeignore

Project-specific exclusions (gitignore syntax):

```gitignore
# Personal files
*-notes.md
TODO-*.md

# Test artifacts
test-results/
.coverage

# Debug output
debug-*.log
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Connection error |

---

## Related Documentation

- [Architecture](../ARCHITECTURE.md) - System overview
- [Memory Guard](MEMORY_GUARD.md) - Quality checks
- [Hooks System](HOOKS.md) - Automation hooks
