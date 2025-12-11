# Configuration Guide

> **Version 3.0** | Unified Configuration System for Claude Indexer

This guide covers the unified configuration system introduced in v3.0, which consolidates all settings into a hierarchical, JSON-based format with full backward compatibility.

---

## Table of Contents

1. [Overview](#overview)
2. [Configuration Locations](#configuration-locations)
3. [Configuration Precedence](#configuration-precedence)
4. [Configuration Sections](#configuration-sections)
5. [Environment Variables](#environment-variables)
6. [Migration Guide](#migration-guide)
7. [Validation](#validation)
8. [Examples](#examples)

---

## Overview

The unified configuration system provides:

- **Hierarchical loading**: Global → Project → Local → Environment → Explicit
- **JSON Schema validation**: IDE autocompletion and validation support
- **Backward compatibility**: Existing `settings.txt` and v2.6 configs still work
- **Separation of concerns**: API keys in global config, project settings in project config
- **Git-friendly**: Local overrides are automatically git-ignored

### Quick Start

```bash
# Initialize a new project with default config
claude-indexer init -p /path/to/project -c my-collection

# Migrate existing configuration to v3.0 format
claude-indexer config migrate

# Validate your configuration
claude-indexer config validate

# Show current configuration with sources
claude-indexer config show --sources
```

---

## Configuration Locations

### Global Configuration (`~/.claude-indexer/`)

User-wide settings that apply to all projects:

```
~/.claude-indexer/
├── config.json          # Global settings (API keys, defaults)
├── rules/               # Global rule overrides
└── .claudeignore        # Global ignore patterns
```

**Example `~/.claude-indexer/config.json`:**

```json
{
  "$schema": "https://claude-code-memory.dev/schemas/unified-config.schema.json",
  "version": "3.0",
  "api": {
    "openai": {
      "apiKey": "sk-..."
    },
    "voyage": {
      "apiKey": "va-...",
      "model": "voyage-3.5-lite"
    },
    "qdrant": {
      "url": "http://localhost:6333"
    }
  },
  "embedding": {
    "provider": "voyage"
  }
}
```

### Project Configuration (`<project>/.claude/`)

Project-specific settings:

```
<project>/.claude/
├── settings.json           # Main project configuration
├── guard.config.json       # Quality guard rules (optional)
├── memory.config.json      # Memory/indexing settings (optional)
├── .claudeignore           # Project-specific ignore patterns
└── settings.local.json     # Local overrides (git-ignored)
```

**Example `.claude/settings.json`:**

```json
{
  "$schema": "https://claude-code-memory.dev/schemas/unified-config.schema.json",
  "version": "3.0",
  "project": {
    "name": "my-awesome-project",
    "collection": "my-awesome-project",
    "description": "A fantastic project"
  },
  "indexing": {
    "filePatterns": {
      "include": ["*.py", "*.js", "*.ts", "*.md"],
      "exclude": ["**/test/**", "**/node_modules/**"]
    },
    "maxFileSize": 2097152
  },
  "watcher": {
    "debounceSeconds": 3.0
  }
}
```

### Local Overrides (`<project>/.claude/settings.local.json`)

Personal settings that shouldn't be committed (automatically git-ignored):

```json
{
  "logging": {
    "debug": true,
    "verbose": true
  },
  "performance": {
    "maxConcurrentFiles": 10
  }
}
```

### Legacy Locations (Backward Compatible)

The system still reads from these locations for backward compatibility:

- `<project>/settings.txt` - Legacy key=value format
- `<project>/.claude-indexer/config.json` - v2.6 ProjectConfig format

---

## Configuration Precedence

Settings are loaded in this order (later sources override earlier):

| Priority | Source | Description |
|----------|--------|-------------|
| 7 | **Defaults** | Built-in default values |
| 6 | **Legacy settings.txt** | Old key=value format (deprecated) |
| 5 | **Global config** | `~/.claude-indexer/config.json` |
| 4 | **Project config** | `.claude/settings.json` |
| 3 | **Local overrides** | `.claude/settings.local.json` |
| 2 | **Environment variables** | `OPENAI_API_KEY`, etc. |
| 1 | **Explicit overrides** | CLI arguments, API parameters |

**Example**: If `api.qdrant.url` is set in global config as `http://localhost:6333` but the environment has `QDRANT_URL=http://cloud.qdrant.io`, the environment variable wins.

---

## Configuration Sections

### `project` - Project Metadata

```json
{
  "project": {
    "name": "my-project",           // Human-readable name
    "collection": "my-project",     // Qdrant collection name
    "description": "Description",   // Optional description
    "projectType": "python"         // python, javascript, typescript, mixed, generic
  }
}
```

### `api` - External Services

```json
{
  "api": {
    "openai": {
      "apiKey": "sk-...",
      "model": "text-embedding-3-small"
    },
    "voyage": {
      "apiKey": "va-...",
      "model": "voyage-3.5-lite"
    },
    "qdrant": {
      "url": "http://localhost:6333",
      "apiKey": ""
    }
  }
}
```

### `embedding` - Embedding Configuration

```json
{
  "embedding": {
    "provider": "voyage",     // "openai" or "voyage"
    "model": null,           // Override provider's default model
    "dimension": 512         // Vector dimension (128-4096)
  }
}
```

### `indexing` - File Indexing Behavior

```json
{
  "indexing": {
    "enabled": true,
    "incremental": true,
    "filePatterns": {
      "include": ["*.py", "*.js", "*.ts", "*.md"],
      "exclude": ["**/node_modules/**", "**/.git/**"]
    },
    "maxFileSize": 1048576,  // 1MB
    "includeTests": false,
    "parserConfig": {
      "javascript": {
        "jsx": true,
        "typescript": true
      }
    }
  }
}
```

### `watcher` - File Watching

```json
{
  "watcher": {
    "enabled": true,
    "debounceSeconds": 2.0,  // 0.1-60.0
    "useGitignore": true
  }
}
```

### `performance` - Performance Tuning

```json
{
  "performance": {
    "batchSize": 100,              // 1-1000
    "initialBatchSize": 25,        // 1-50
    "batchSizeRampUp": true,
    "maxConcurrentFiles": 5,       // 1-100
    "useParallelProcessing": true,
    "maxParallelWorkers": 0,       // 0 = auto (CPU count - 1)
    "cleanupIntervalMinutes": 1    // 0 = disabled
  }
}
```

### `hooks` - Claude Code Hooks

```json
{
  "hooks": {
    "enabled": true,
    "postToolUse": [
      {
        "matcher": "Write|Edit",
        "command": ".claude/hooks/after-write.sh",
        "enabled": true,
        "timeout": 30000
      }
    ],
    "stop": [
      {
        "matcher": "*",
        "command": ".claude/hooks/end-of-turn-check.sh"
      }
    ],
    "sessionStart": []
  }
}
```

### `guard` - Quality Guard

```json
{
  "guard": {
    "enabled": true,
    "rules": {
      "sql_injection": {
        "enabled": true,
        "severity": "CRITICAL"
      },
      "debug_statements": {
        "enabled": true,
        "severity": "MEDIUM",
        "autoFix": true
      }
    },
    "severityThresholds": {
      "block": "HIGH",
      "warn": "MEDIUM"
    }
  }
}
```

### `logging` - Logging Configuration

```json
{
  "logging": {
    "level": "INFO",       // DEBUG, INFO, WARNING, ERROR
    "verbose": true,
    "debug": false,
    "logFile": null        // Optional log file path
  }
}
```

---

## Environment Variables

| Variable | Config Path | Description |
|----------|-------------|-------------|
| `OPENAI_API_KEY` | `api.openai.apiKey` | OpenAI API key |
| `VOYAGE_API_KEY` | `api.voyage.apiKey` | Voyage AI API key |
| `QDRANT_API_KEY` | `api.qdrant.apiKey` | Qdrant API key |
| `QDRANT_URL` | `api.qdrant.url` | Qdrant server URL |
| `EMBEDDING_PROVIDER` | `embedding.provider` | Provider (openai/voyage) |
| `VOYAGE_MODEL` | `api.voyage.model` | Voyage model name |
| `CLAUDE_INDEXER_DEBUG` | `logging.debug` | Enable debug mode |
| `CLAUDE_INDEXER_VERBOSE` | `logging.verbose` | Enable verbose output |
| `CLAUDE_INDEXER_COLLECTION` | `project.collection` | Collection name |

**Example usage:**

```bash
export VOYAGE_API_KEY="va-..."
export EMBEDDING_PROVIDER="voyage"
claude-indexer index -p . -c my-project
```

---

## Migration Guide

### From settings.txt

The old `settings.txt` format is still supported but deprecated. To migrate:

```bash
# Analyze what would be migrated
claude-indexer config migrate --dry-run

# Perform migration (creates backup automatically)
claude-indexer config migrate

# Force overwrite existing config
claude-indexer config migrate --force
```

**Key mappings from settings.txt:**

| Old Key | New Path |
|---------|----------|
| `openai_api_key` | `api.openai.apiKey` |
| `voyage_api_key` | `api.voyage.apiKey` |
| `qdrant_url` | `api.qdrant.url` |
| `embedding_provider` | `embedding.provider` |
| `debounce_seconds` | `watcher.debounceSeconds` |
| `batch_size` | `performance.batchSize` |

### From .claude-indexer/config.json (v2.6)

V2.6 configs are automatically converted to v3.0 format when loaded:

```bash
# Check current version
cat .claude-indexer/config.json | jq '.version'

# Migrate to new format
claude-indexer config migrate
```

### Backup and Restore

Migrations automatically create backups:

```bash
# List available backups
claude-indexer config backups

# Restore from backup
claude-indexer config restore --timestamp 20240115_143022

# Restore most recent backup
claude-indexer config restore
```

---

## Validation

### Validate Configuration

```bash
# Validate current project config
claude-indexer config validate

# Validate specific file
claude-indexer config validate /path/to/settings.json

# Show detailed validation output
claude-indexer config validate --verbose
```

### Common Validation Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Missing required field: project.collection" | No collection specified | Add `project.collection` to config |
| "Invalid Qdrant URL" | URL doesn't start with http(s):// | Fix the URL format |
| "OpenAI API key not configured" | Using OpenAI provider without key | Set `OPENAI_API_KEY` or add to config |

### JSON Schema for IDE Support

Add schema reference for IDE autocompletion:

```json
{
  "$schema": "https://claude-code-memory.dev/schemas/unified-config.schema.json",
  "version": "3.0",
  ...
}
```

---

## Examples

### Minimal Configuration

```json
{
  "version": "3.0",
  "project": {
    "name": "my-project",
    "collection": "my-project"
  }
}
```

### Python Project

```json
{
  "$schema": "https://claude-code-memory.dev/schemas/unified-config.schema.json",
  "version": "3.0",
  "project": {
    "name": "python-api",
    "collection": "python-api",
    "projectType": "python"
  },
  "indexing": {
    "filePatterns": {
      "include": ["*.py", "*.md", "*.yaml", "*.json"],
      "exclude": [
        "__pycache__/", "*.pyc", ".venv/", ".tox/",
        "*.egg-info/", "dist/", "build/"
      ]
    },
    "includeTests": false,
    "parserConfig": {
      "python": {
        "includeDocstrings": true,
        "includeTypeHints": true
      }
    }
  }
}
```

### TypeScript/React Project

```json
{
  "$schema": "https://claude-code-memory.dev/schemas/unified-config.schema.json",
  "version": "3.0",
  "project": {
    "name": "react-app",
    "collection": "react-app",
    "projectType": "typescript"
  },
  "indexing": {
    "filePatterns": {
      "include": ["*.ts", "*.tsx", "*.js", "*.jsx", "*.json", "*.md"],
      "exclude": [
        "node_modules/", "dist/", "build/", ".next/",
        "*.min.js", "*.d.ts"
      ]
    },
    "parserConfig": {
      "javascript": {
        "jsx": true,
        "typescript": true
      }
    }
  },
  "watcher": {
    "debounceSeconds": 1.5
  }
}
```

### CI/CD Configuration

For CI environments, use environment variables:

```yaml
# GitHub Actions example
env:
  VOYAGE_API_KEY: ${{ secrets.VOYAGE_API_KEY }}
  QDRANT_URL: ${{ secrets.QDRANT_URL }}
  QDRANT_API_KEY: ${{ secrets.QDRANT_API_KEY }}
  EMBEDDING_PROVIDER: voyage

steps:
  - name: Index codebase
    run: claude-indexer index -p . -c ${{ github.repository }}
```

---

## Troubleshooting

### Configuration Not Loading

```bash
# Show which config files are being loaded
claude-indexer config show --sources

# Enable debug logging
CLAUDE_INDEXER_DEBUG=true claude-indexer index -p .
```

### Validation Errors

```bash
# Get detailed validation output
claude-indexer config validate --verbose

# Check JSON syntax
python -m json.tool .claude/settings.json
```

### Migration Issues

```bash
# Analyze without making changes
claude-indexer config migrate --dry-run

# Force migration (overwrites existing)
claude-indexer config migrate --force

# Skip backup (not recommended)
claude-indexer config migrate --no-backup
```

---

## Related Documentation

- [CLI Reference](CLI_REFERENCE.md) - Complete CLI command documentation
- [Hooks System](HOOKS.md) - Claude Code hooks configuration
- [Memory Guard](MEMORY_GUARD.md) - Quality guard rules
- [UI Consistency Guide](UI_CONSISTENCY_GUIDE.md) - UI quality checking

---

*For issues or questions, see the [troubleshooting guide](CLI_REFERENCE.md#troubleshooting) or open an issue on GitHub.*
