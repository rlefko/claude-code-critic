# Changelog

All notable changes to Claude Code Memory are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.9.18] - 2024-12-12

### Added
- **User Experience Polish (Milestone 6.2)** - Complete CLI UX improvements
  - **OutputManager** (`claude_indexer/cli/output.py`): Centralized output with color/quiet mode support
  - **CLIError Types** (`claude_indexer/cli/errors.py`): Structured errors with categories and suggestions
  - **StatusCollector** (`claude_indexer/cli/status.py`): Unified system health status aggregation
  - **`claude-indexer status` command**: Shows Qdrant, Service, Hooks, Index, and Health status

### Enhanced
- **NO_COLOR Support** - Respects [no-color.org](https://no-color.org/) standard
  - `--no-color` flag added to all CLI commands
  - Automatic detection of `NO_COLOR` and `FORCE_COLOR` environment variables
  - Accessible symbol fallbacks: `[OK]`, `[FAIL]`, `[WARN]`, `[INFO]`
- **Quiet Mode** (`-q/--quiet`) - Suppresses info output, errors always shown
- **Progress Bar** - Added `quiet` and `use_color` parameters for consistent UX
- **Error Messages** - All errors include actionable suggestions

### Testing
- 102 new unit tests in `tests/unit/cli/` (output, errors, status modules)
- All tests passing with comprehensive coverage

---

## [2.9.12] - 2024-12-11

### Added
- **Project Templates (Milestone 4.3)** - Project-type-specific templates for `claude-indexer init`
  - **Python templates**: `__pycache__/`, `.venv/`, `.pytest_cache/`, deserialization rules
  - **JavaScript templates**: `node_modules/`, npm logs, XSS and eval detection
  - **TypeScript templates**: `*.tsbuildinfo`, type safety rules (`@ts-ignore`, `any` type)
  - **React/Frontend templates**: `.next/`, `.nuxt/`, `.vercel/`, accessibility rules (shared by Next.js, Vue)
  - **Generic templates**: Minimal fallback patterns for unknown project types

### Enhanced
- **TemplateManager** - Project-type-aware template resolution with fallback chain
  - Resolution order: `templates/{project_type}/{template}` → `templates/{template}`
  - `TYPE_DIR_MAP` maps project types to template directories
  - Next.js and Vue share React templates (common frontend patterns)
- **FileGenerator** - Updated to use project-type templates for `.claudeignore` and `guard.config.json`
  - Shows template type in success messages (e.g., "Created ... (python template)")
  - Graceful fallback to root templates or programmatic generation

### Testing
- 30 new unit tests for project-type template resolution and file generation
- Tests verify language-specific patterns in generated files
- All 63 init module tests passing

---

## [2.8.0] - 2024-12-08

### Added
- **Batch Indexing** (`--files-from-stdin`) - 4-15x faster git hooks through batch file processing
- **SessionStart Hook** - Immediate project context injection on session start
- **UserPromptSubmit Hook** - Smart prompt analysis with MCP tool suggestions
- **10 Slash Commands** - Complete code analysis suite (`/refactor`, `/restructure`, `/redocument`, `/resecure`, `/reresilience`, `/reoptimize`, `/retype`, `/retest`, `/rebuild`, `/resolve`)

### Enhanced
- **Memory Guard v4.3** - 27 pattern-based checks across 5 categories
- **Two-Mode Architecture** - FAST mode (<300ms) for editing, FULL mode for commits
- **Setup Infrastructure** - Complete CLAUDE.md template with Memory Guard documentation
- **Git Hooks** - Diff-aware indexing (only changed files, not entire project)

### Performance
- Batch indexing reduces hook latency from 60s to 5s for 10 files
- SessionStart hook completes in <100ms
- UserPromptSubmit hook completes in <50ms

---

## [2.7.0] - 2024-11

### Added
- **Entity-Specific Graph Filtering** - Focus queries on specific entities with `entity` parameter
- **Progressive Disclosure** - Metadata-first responses with on-demand implementation details
- **Parallel Hybrid Search** - Concurrent semantic + BM25 search execution
- **Multi-Collection Support** - Memory Guard works across multiple project collections

### Enhanced
- **read_graph Tool** - Four modes: `smart`, `entities`, `relationships`, `raw`
- **get_implementation Tool** - Three scopes: `exact`, `logical`, `dependencies`
- **Cache Exclusion Safety** - Prevents stale data in search results

### Performance
- Metadata search: 3-5ms (previously 50-100ms)
- Parallel search: 30% faster than sequential
- AST parse cache: Reduced redundant parsing

---

## [2.6.0] - 2024-10

### Added
- **BM25 Hybrid Search** - OkapiBM25 algorithm with RRF fusion (70% semantic + 30% keyword)
- **Unified entityTypes Filtering** - Single parameter supports both entity and chunk types with OR logic
- **Search Modes** - `hybrid` (default), `semantic`, `keyword`

### Enhanced
- **Token Management** - 25k token compliance with 96% safety margin
- **Auto-Reduce Mechanism** - Exponential backoff (0.7 factor, 10 max attempts)
- **Streaming Response Builder** - Efficient large response handling

### Fixed
- Critical BM25 performance issue causing OOM crashes
- Sparse vector configuration bugs

---

## [2.5.0] - 2024-09

### Added
- **Multi-Project Support** - Per-collection configuration with unique MCP servers
- **Setup Script** - One-command installation with `./setup.sh`
- **Exclusion System** - `.claudeignore` with gitignore-style patterns
- **Binary Detection** - Automatic exclusion via magic number detection

### Enhanced
- **Collection Naming** - Sanitized project names for Qdrant compatibility
- **MCP Configuration** - Auto-generated `.mcp.json` with project-specific settings

### Fixed
- Race condition in Qdrant collection creation with sparse vectors
- CachingEmbedder parameter errors

---

## [2.4.0] - 2024-08

### Added
- **Memory Guard System** - AI-powered code quality enforcement
- **Tier Architecture** - 3-tier analysis (trivial skip, fast detection, full analysis)
- **Duplicate Detection** - Signature hash + semantic similarity matching

### Enhanced
- **Voyage AI Integration** - 85% cost reduction with voyage-3-lite
- **Embedding Batching** - 500 relations / 100 entities per API call

### Performance
- 75% fewer API calls through batching
- Optimized tokenization to reduce rate limiting

---

## [2.3.0] - 2024-07

### Added
- **Parallel File Processing** - Multiprocessing for large batches (100+ files)
- **Progress Tracking** - Real-time progress bars with ETA
- **Memory Monitoring** - 2GB threshold with automatic batch reduction

### Enhanced
- **File Categorization** - 3-tier system (Light/Standard/Deep) based on complexity
- **Batch Optimization** - Dynamic sizing (50→25, initial: 10→5)

### Fixed
- WAL corruption issues in Qdrant
- Memory management for large projects

---

## [2.2.0] - 2024-06

### Added
- **Indexing Optimizations** - Large-project support with fallback parser
- **Health Checks** - Python 3.12 verification during setup
- **Cross-Platform Support** - macOS and Linux compatibility

### Enhanced
- **Setup Script** - Comprehensive environment validation
- **Error Handling** - Graceful degradation for parse failures

---

## [2.1.0] - 2024-05

### Added
- **Web Explorer** - React-based visualization UI
- **D3.js Graph** - Interactive entity relationship visualization
- **Monaco Editor** - Code viewing with syntax highlighting

### Enhanced
- **API Endpoints** - FastAPI backend for web interface
- **Real-Time Updates** - WebSocket support for live changes

---

## [2.0.0] - 2024-04

### Added
- **MCP Protocol Support** - Model Context Protocol integration
- **Qdrant Backend** - Vector database for semantic storage
- **Tree-sitter Parsing** - Multi-language AST analysis

### Changed
- **Architecture Rewrite** - Separated indexer and MCP server
- **Embedding Model** - Switched to Voyage AI (voyage-3-lite)

### Removed
- Legacy JSON-only storage
- Single-file embedding approach

---

## [1.0.0] - 2024-03

### Added
- Initial release
- Basic semantic code indexing
- Python and JavaScript support
- Simple vector search

---

## Version Highlights

| Version | Key Feature | Impact |
|---------|-------------|--------|
| 2.8.0 | Batch Indexing | 4-15x faster git hooks |
| 2.7.0 | Progressive Disclosure | 90% faster searches |
| 2.6.0 | Hybrid Search | Better result relevance |
| 2.5.0 | Multi-Project | Team-scale deployment |
| 2.4.0 | Memory Guard | Code quality automation |
| 2.3.0 | Parallel Processing | Large project support |
| 2.0.0 | MCP + Qdrant | Modern architecture |

---

## Migration Notes

### From 2.7.x to 2.8.x
- **Git hooks updated**: Run `./setup.sh` to install new batch indexing hooks
- **New hooks available**: SessionStart and UserPromptSubmit hooks added
- **Slash commands**: Copy `.claude/commands/` to your project

### From 2.6.x to 2.7.x
- **No breaking changes**: Progressive disclosure is automatic
- **Optional**: Use `entity` parameter in `read_graph` for focused queries

### From 2.5.x to 2.6.x
- **Search mode default**: Changed from `semantic` to `hybrid`
- **Optional**: Specify `searchMode="semantic"` for previous behavior

### From 1.x to 2.x
- **Full reindex required**: New vector format incompatible
- **Configuration**: Migrate to `.mcp.json` format
- **Dependencies**: Install Qdrant and Voyage AI credentials
