# Enhanced Claude Code Memory and Quality Guard System

## Implementation Milestones

> **Version**: 1.0
> **Based On**: PRD.md and TDD.md
> **Target**: Extend `claude-indexer` CLI for all developers (zero-friction onboarding)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Phase 0: Foundation & Infrastructure](#phase-0-foundation--infrastructure)
3. [Phase 1: Memory System & Indexing Pipeline](#phase-1-memory-system--indexing-pipeline)
4. [Phase 2: Quality Guard & Rule Engine](#phase-2-quality-guard--rule-engine)
5. [Phase 3: Hook System Integration](#phase-3-hook-system-integration)
6. [Phase 4: One-Command Onboarding](#phase-4-one-command-onboarding)
7. [Phase 5: Multi-Repository Support](#phase-5-multi-repository-support)
8. [Phase 6: Polish & Optimization](#phase-6-polish--optimization)
9. [Appendix: Rule Specifications](#appendix-rule-specifications)

---

## Executive Summary

### Vision
Create a "magical" developer experience where Claude Code acts as an expert pair-programmer with persistent memory and automatic quality enforcement. The system catches issues before they enter the codebase while remaining invisible during normal development.

### Current State (90-95% Complete)
| Component | Status | Notes |
|-----------|--------|-------|
| CLI Infrastructure | ✅ Complete | `claude-indexer` with 20+ commands |
| Qdrant Integration | ✅ Complete | Hybrid search (semantic + BM25) |
| MCP Server | ✅ Complete | 8+ tools, streaming responses |
| Hook Framework | ✅ Complete | PreToolUse, Stop, SessionStart |
| UI Consistency | ✅ Complete | 15+ rules, 3-tier architecture |
| Memory Guard v4.3 | ✅ Complete | 21+ pattern checks |
| Multi-language Parser | ✅ Complete | 7 languages supported |
| **Bulk Indexing Pipeline** | ✅ Complete | IndexingPipeline with resume capability (v2.9) |
| **Incremental Indexing** | ✅ Complete | Git-aware updates with hash fallback (v2.9.1) |
| **Rule Engine Framework** | ✅ Complete | BaseRule, RuleEngine, discovery, config (v2.9.2) |
| **Security Rules (11)** | ✅ Complete | All 11 OWASP rules implemented (v2.9.3) |
| **Tech Debt Rules (11)** | ✅ Complete | All 11 rules implemented (v2.9.5) |
| **Core PRD Rules (6)** | ✅ Complete | Token drift, duplication, unsafe (v2.9.5) |
| **PostToolUse Hook** | ✅ Complete | Fast rules (<30ms), async indexing queue (v2.9.7) |
| **Stop Hook (End of Turn)** | ✅ Complete | Comprehensive checks (<5s), diff-aware, exit code 2 blocking (v2.9.8) |
| **Claude Self-Repair Loop** | ✅ Complete | Retry tracking, escalation, fix suggestions (v2.9.9) |
| **One-Command Init** | ✅ Complete | Full `claude-indexer init` with all components (v2.9.10) |
| **Dependency Verification** | ✅ Complete | `claude-indexer doctor` with 8 checks, suggestions (v2.9.11) |
| **Project Templates** | ✅ Complete | 5 project-type templates with fallback (v2.9.12) |
| **SessionStart Hook** | ✅ Complete | Health checks, index freshness, welcome message (v2.9.13) |
| **Collection Isolation** | ✅ Complete | Multi-tenancy naming, CLI management, cleanup (v2.9.14) |
| **Session Isolation** | ✅ Complete | Session-scoped config, CWD detection, file locking (v2.9.15) |
| **Workspace Support** | ✅ Complete | Monorepo + VS Code multi-root detection, per-folder config (v2.9.16) |
| All 27 Rules | ✅ Complete | 27+ rules implemented |
| Multi-Repo Isolation | ✅ Complete | Collection + session + workspace isolation complete |

### Success Metrics (from PRD)
- **Critical Issues Blocked**: >95% of serious issues caught before commit
- **User Interruption Rate**: <10% of turns trigger guard intervention
- **Setup Time**: <5 minutes for any project
- **Performance Overhead**: <5s for end-of-turn checks
- **Token Savings**: 20% reduction via memory reuse

---

## Phase 0: Foundation & Infrastructure

**Goal**: Establish the architectural foundation and ensure all prerequisite systems are production-ready.

### Milestone 0.1: Configuration System Consolidation

**Objective**: Create a unified, hierarchical configuration system.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 0.1.1 | Design unified config schema (JSON Schema) | HIGH | DONE |
| 0.1.2 | Create `claude_indexer/config/unified_config.py` | HIGH | DONE |
| 0.1.3 | Implement hierarchical loading: global → project → local | HIGH | DONE |
| 0.1.4 | Add config validation with clear error messages | MEDIUM | DONE |
| 0.1.5 | Create config migration tool for existing setups | MEDIUM | DONE |
| 0.1.6 | Document config options in `docs/CONFIGURATION.md` | MEDIUM | DONE |

**Configuration Files**:
```
~/.claude-indexer/                    # Global config
├── config.json                       # Global settings
├── rules/                            # Global rule overrides
└── .claudeignore                     # Global ignore patterns

<project>/.claude/                    # Project config
├── settings.json                     # Project settings (hooks, permissions)
├── guard.config.json                 # Guard rules & thresholds
├── memory.config.json                # Memory/indexing settings
└── .claudeignore                     # Project-specific ignores

<project>/.claude/settings.local.json # Local overrides (git-ignored)
```

**Testing Requirements**:
- [x] Unit tests for config loader (`tests/unit/test_config_loader.py`)
- [x] Integration tests for hierarchical merging
- [x] Edge cases: missing files, invalid JSON, conflicting values

**Documentation**:
- [x] `docs/CONFIGURATION.md` with all options
- [x] Migration guide from current settings

**Success Criteria**:
- Single source of truth for all configuration
- Backward compatible with existing `settings.txt`
- Clear error messages for invalid configs

---

### Milestone 0.2: .claudeignore System

**Objective**: Implement comprehensive file ignore system that works across all components.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 0.2.1 | Create `.claudeignore` parser (gitignore-compatible) | HIGH | DONE |
| 0.2.2 | Integrate with indexer (skip ignored files) | HIGH | DONE |
| 0.2.3 | Integrate with MCP server (filter search results) | HIGH | DONE |
| 0.2.4 | Create default `.claudeignore` template | MEDIUM | DONE |
| 0.2.5 | Add CLI command: `claude-indexer ignore [pattern]` | LOW | DONE |
| 0.2.6 | Implement hierarchical ignore (global + project) | MEDIUM | DONE |

**Default .claudeignore Template**:
```gitignore
# Secrets & Credentials
.env
.env.*
*.pem
*.key
**/credentials.json
**/secrets/

# Large/Binary Files
*.db
*.sqlite
*.log
node_modules/
.venv/
__pycache__/

# Build Artifacts
dist/
build/
*.pyc
```

**Testing Requirements**:
- [x] Unit tests for pattern matching
- [x] Integration tests with indexer
- [x] Test inheritance (global + project)

**Documentation**:
- [x] `.claudeignore` format specification
- [x] Common patterns for different project types

**Success Criteria**:
- Secrets never indexed or searchable
- Pattern matching identical to `.gitignore`
- Clear feedback when files are ignored

---

### Milestone 0.3: Logging & Debugging Infrastructure

**Objective**: Establish comprehensive logging for troubleshooting and performance monitoring.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 0.3.1 | Create unified logging module (`claude_indexer/indexer_logging.py`) | HIGH | DONE |
| 0.3.2 | Implement log rotation (3-file, size-based) | MEDIUM | DONE |
| 0.3.3 | Add structured logging (JSON format option) | MEDIUM | DONE |
| 0.3.4 | Create debug mode with verbose output | HIGH | DONE |
| 0.3.5 | Add performance timing decorators | MEDIUM | DONE |
| 0.3.6 | Implement log aggregation for multi-component debugging | LOW | DONE |

**Implementation Details**:
- Enhanced `indexer_logging.py` with JSONFormatter, debug_context(), category loggers
- Extended `LoggingConfig` in `unified_config.py` with format, rotation_count, max_bytes fields
- Created `performance.py` with @timed decorator, PerformanceTimer, PerformanceAggregator
- Unit tests: `tests/unit/test_logging.py` (33 tests)

**Log Locations**:
```
~/.claude-indexer/logs/
├── indexer.log           # Indexing operations
├── guard.log             # Quality guard decisions
├── mcp.log               # MCP server requests
└── performance.log       # Timing metrics

<project>/logs/
└── <collection>.log      # Project-specific logs
```

**Testing Requirements**:
- [x] Verify log rotation works correctly
- [x] Test debug mode activation
- [x] Ensure no sensitive data in logs

**Success Criteria**:
- All components log to consistent format
- Performance issues identifiable from logs
- Debug mode provides actionable information

---

## Phase 1: Memory System & Indexing Pipeline

**Goal**: Build the complete semantic memory system with efficient indexing.

### Milestone 1.1: Bulk Indexing Engine

**Objective**: Create efficient initial repository indexing.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 1.1.1 | Create `IndexingPipeline` class in `claude_indexer/indexing/pipeline.py` | HIGH | DONE |
| 1.1.2 | Implement parallel file processing (thread pool) | HIGH | DONE |
| 1.1.3 | Add intelligent chunking (function/class boundaries) | HIGH | DONE |
| 1.1.4 | Implement embedding batching (reduce API calls) | HIGH | DONE |
| 1.1.5 | Create progress reporter with ETA | MEDIUM | DONE |
| 1.1.6 | Add resume capability for interrupted indexing | MEDIUM | DONE |
| 1.1.7 | Implement file hash caching (skip unchanged) | HIGH | DONE |

**Architecture**:
```python
class IndexingPipeline:
    def __init__(self, config: UnifiedConfig):
        self.parser_registry = ParserRegistry()
        self.embedder = EmbeddingEngine(config)
        self.storage = QdrantStorage(config)
        self.cache = IndexCache(config.cache_dir)

    def index_repository(self, path: Path, mode: str = "auto") -> IndexResult:
        """Full or incremental index based on mode and cache state."""
        pass

    def index_files(self, files: List[Path]) -> IndexResult:
        """Index specific files (for incremental updates)."""
        pass
```

**Testing Requirements**:
- [x] Unit tests for each component (83 tests in tests/unit/indexing/)
- [ ] Integration test: index small repo (<100 files)
- [ ] Performance test: index medium repo (<1000 files) in <2min
- [ ] Test resume after interruption

**Documentation**:
- [ ] Update `docs/CLI_REFERENCE.md` with indexing commands
- [ ] Add troubleshooting guide for common indexing issues

**Success Criteria**:
- Index 1000 files in <2 minutes
- <1% duplicate chunks in database
- Clear progress feedback

**Implementation Notes (v2.9)**:
- Created `claude_indexer/indexing/` package with modular components:
  - `types.py`: PipelineConfig, PipelineResult, ProgressState, CheckpointState, BatchMetrics
  - `pipeline.py`: Main IndexingPipeline orchestrator
  - `progress.py`: PipelineProgress with ETA and terminal visualization
  - `checkpoint.py`: IndexingCheckpoint for resume capability
  - `batch_optimizer.py`: BatchOptimizer with memory-aware adaptive sizing
- Integrated with CoreIndexer via `index_project_with_pipeline()` method
- Added `_get_pipeline()` lazy initialization for backward compatibility
- Checkpoint files stored in `.index_cache/indexing_checkpoint_{collection}.json`
- Atomic writes using temp file + rename pattern

---

### Milestone 1.2: Incremental Indexing (Git-Aware)

**Objective**: Efficiently update index when files change.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 1.2.1 | Create `GitChangeDetector` class | HIGH | DONE |
| 1.2.2 | Implement `get_changed_files(since_commit)` | HIGH | DONE |
| 1.2.3 | Add file hash comparison fallback (non-git repos) | MEDIUM | DONE |
| 1.2.4 | Create batch update processor | HIGH | DONE |
| 1.2.5 | Handle file deletions (remove from index) | HIGH | DONE |
| 1.2.6 | Handle file renames (preserve history) | MEDIUM | DONE |
| 1.2.7 | Add `--files-from-stdin` for hook integration | HIGH | DONE |

**Git Integration**:
```python
class GitChangeDetector:
    def get_changed_since(self, commit_sha: str) -> ChangeSet:
        """Get files changed since a specific commit."""
        pass

    def get_staged_files(self) -> List[Path]:
        """Get currently staged files (for pre-commit)."""
        pass

    def get_branch_diff(self, base: str, head: str) -> ChangeSet:
        """Get files changed between branches."""
        pass
```

**Testing Requirements**:
- [x] Test with various git operations (commit, merge, rebase, checkout)
- [x] Test non-git repository fallback
- [x] Test file rename tracking

**Documentation**:
- [x] Document git integration behavior
- [x] Troubleshooting for git-related issues

**Success Criteria**:
- Incremental update <1s for single file
- Correct handling of all git operations
- Non-git repos still work via hash comparison

**Implementation Notes (v2.9.1)**:
- Created `claude_indexer/git/` package with:
  - `change_detector.py`: GitChangeDetector class for git-aware change detection
  - `ChangeSet` dataclass for tracking added/modified/deleted/renamed files
- Added `update_file_paths()` to QdrantStore for efficient rename handling
- Added `index_incremental()` to CoreIndexer for git-aware indexing workflow
- CLI enhancements: `--since`, `--staged`, `--pr-diff` options
- Hash-based fallback using FileHashCache for non-git repos
- State file tracks `_last_indexed_commit` for automatic incremental detection
- Unit tests: 36 tests in `tests/unit/test_git_change_detector.py`
- Integration tests: 9 tests in `tests/integration/test_incremental_indexing.py`

---

### Milestone 1.3: Memory Query Interface

**Objective**: Provide efficient semantic search with progressive disclosure.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 1.3.1 | Verify hybrid search (semantic + BM25) works correctly | HIGH | DONE |
| 1.3.2 | Implement metadata-first search (90% speed boost) | HIGH | DONE |
| 1.3.3 | Add implementation chunk retrieval on-demand | HIGH | DONE |
| 1.3.4 | Create entity-specific graph filtering | HIGH | DONE |
| 1.3.5 | Add search result caching (LRU, configurable TTL) | MEDIUM | NEW |
| 1.3.6 | Implement search analytics (track popular queries) | LOW | NEW |

**Testing Requirements**:
- [ ] Benchmark search latency (<50ms for metadata, <200ms with implementation)
- [ ] Test filter combinations (entity types, chunk types)
- [ ] Verify cache invalidation on index updates

**Documentation**:
- [ ] Update MCP tool documentation with examples
- [ ] Add search optimization guide

**Success Criteria**:
- Metadata search <50ms
- Full search <200ms
- Cache hit rate >60% for repeated queries

---

### Milestone 1.4: Memory Persistence & Backup

**Objective**: Ensure memory survives system changes and can be backed up.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 1.4.1 | Verify Qdrant persistence configuration | HIGH | DONE |
| 1.4.2 | Create backup command: `claude-indexer backup` | MEDIUM | PARTIAL |
| 1.4.3 | Create restore command: `claude-indexer restore` | MEDIUM | PARTIAL |
| 1.4.4 | Add manual entry preservation during re-index | HIGH | DONE |
| 1.4.5 | Implement collection migration tool | LOW | NEW |

**Testing Requirements**:
- [ ] Test backup/restore cycle
- [ ] Verify manual entries preserved
- [ ] Test collection migration

**Documentation**:
- [ ] Backup/restore procedures
- [ ] Disaster recovery guide

**Success Criteria**:
- Zero data loss during re-indexing
- Backup completes in <5min for typical project
- Manual entries always preserved

---

## Phase 2: Quality Guard & Rule Engine

**Goal**: Implement all 27 quality rules with the modular rule engine.

### Milestone 2.1: Rule Engine Framework

**Objective**: Create extensible rule engine that supports all rule types.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 2.1.1 | Create `BaseRule` abstract class | HIGH | DONE |
| 2.1.2 | Create `RuleEngine` coordinator | HIGH | DONE |
| 2.1.3 | Implement rule discovery (auto-load from directory) | HIGH | DONE |
| 2.1.4 | Add rule configuration (enable/disable, thresholds) | HIGH | DONE |
| 2.1.5 | Create `RuleContext` with diff, memory access | HIGH | DONE |
| 2.1.6 | Implement severity levels (CRITICAL, HIGH, MEDIUM, LOW) | HIGH | DONE |
| 2.1.7 | Add auto-fix capability to rule interface | MEDIUM | DONE |

**Rule Interface**:
```python
class BaseRule(ABC):
    name: str
    severity: Severity
    category: str  # security, tech_debt, resilience, documentation
    trigger: Trigger  # on_write, on_stop, on_commit

    @abstractmethod
    def check(self, context: RuleContext) -> List[Finding]:
        """Run the rule check, return findings."""
        pass

    def can_auto_fix(self) -> bool:
        """Whether this rule can auto-fix violations."""
        return False

    def auto_fix(self, finding: Finding) -> Optional[Fix]:
        """Generate auto-fix if possible."""
        return None
```

**Testing Requirements**:
- [x] Unit tests for rule engine
- [x] Test rule discovery mechanism
- [x] Test severity filtering

**Documentation**:
- [ ] Rule authoring guide in `docs/RULE_AUTHORING.md`
- [ ] Rule configuration reference

**Success Criteria**:
- New rules can be added without code changes
- Rules configurable via JSON
- Clear finding messages

**Implementation Notes (v2.9.2)**:
- Created `claude_indexer/rules/` package with modular components:
  - `base.py`: Severity, Trigger, DiffHunk, Evidence, Finding, RuleContext, BaseRule
  - `engine.py`: RuleEngine coordinator with RuleEngineResult, RuleError, RuleExecutionResult
  - `discovery.py`: RuleDiscovery for auto-loading rules from category directories
  - `config.py`: RuleConfig, CategoryConfig, PerformanceConfig, RuleEngineConfig, RuleEngineConfigLoader
  - `fix.py`: AutoFix dataclass with apply() method for automatic fixes
- Category directories: `security/`, `tech_debt/`, `resilience/`, `documentation/`, `git/`
- Proof-of-concept rules implemented:
  - `TECH_DEBT.TODO_MARKERS` - Detects TODO, FIXME, HACK markers
  - `TECH_DEBT.FIXME_MARKERS` - High-severity FIXME detection
  - `TECH_DEBT.DEBUG_STATEMENTS` - Detects print(), console.log(), debugger
  - `TECH_DEBT.BREAKPOINTS` - High-severity breakpoint detection
  - `GIT.FORCE_PUSH` - Detects git push --force commands
  - `GIT.HARD_RESET` - Detects git reset --hard commands
  - `GIT.DESTRUCTIVE_OPS` - Detects rm -rf and other dangerous commands
- Unit tests: 92 tests in `tests/unit/rules/` (all passing)
- Configuration via `guard.config.json` with hierarchical merging (global → project → local)

---

### Milestone 2.2: Security Rules (11 Rules)

**Objective**: Implement all security-focused quality checks.

#### Tasks

| ID | Task | Priority | Rule Name | Status |
|----|------|----------|-----------|--------|
| 2.2.1 | SQL Injection Detection | CRITICAL | `sql_injection` | DONE |
| 2.2.2 | XSS Detection | CRITICAL | `xss_vulnerability` | DONE |
| 2.2.3 | Command Injection Detection | CRITICAL | `command_injection` | DONE |
| 2.2.4 | Hardcoded Secrets Detection | CRITICAL | `hardcoded_secrets` | DONE |
| 2.2.5 | Insecure Crypto Detection | HIGH | `insecure_crypto` | DONE |
| 2.2.6 | Path Traversal Detection | HIGH | `path_traversal` | DONE |
| 2.2.7 | Insecure Deserialization | HIGH | `insecure_deserialize` | DONE |
| 2.2.8 | Missing Authentication | HIGH | `missing_auth` | DONE |
| 2.2.9 | Sensitive Data Exposure | MEDIUM | `sensitive_exposure` | DONE |
| 2.2.10 | Insecure Random | MEDIUM | `insecure_random` | DONE |
| 2.2.11 | Missing HTTPS | MEDIUM | `missing_https` | DONE |

**Implementation Location**: `claude_indexer/rules/security/`

**Testing Requirements**:
- [x] Unit tests for each rule with positive/negative cases (57 tests)
- [x] Test with real-world vulnerable code samples
- [x] False positive rate <5%

**Documentation**:
- [ ] Security rule reference in `docs/MEMORY_GUARD.md`
- [ ] Examples of detected patterns

**Success Criteria**:
- [x] All OWASP Top 10 covered
- [x] <5% false positive rate
- [x] Clear remediation guidance

---

### Milestone 2.3: Tech Debt Rules (9 Rules)

**Objective**: Implement technical debt detection rules.

#### Tasks

| ID | Task | Priority | Rule Name | Status |
|----|------|----------|-----------|--------|
| 2.3.1 | TODO/FIXME/HACK Detection | MEDIUM | `todo_markers` | DONE |
| 2.3.2 | Debug Statement Detection | MEDIUM | `debug_statements` | DONE |
| 2.3.3 | Commented Code Detection | LOW | `commented_code` | DONE |
| 2.3.4 | Dead Code Detection | MEDIUM | `dead_code` | DONE |
| 2.3.5 | Overly Complex Functions | MEDIUM | `complexity` | DONE |
| 2.3.6 | Large Files Detection | LOW | `large_files` | DONE |
| 2.3.7 | Magic Numbers Detection | LOW | `magic_numbers` | DONE |
| 2.3.8 | Inconsistent Naming | MEDIUM | `naming_conventions` | DONE |
| 2.3.9 | Deprecated API Usage | MEDIUM | `deprecated_apis` | DONE |

**Implementation Location**: `claude_indexer/rules/tech_debt/`

**Testing Requirements**:
- [x] Unit tests for each rule (38 tests in `tests/unit/rules/test_tech_debt_rules.py`)
- [x] Test threshold configurations
- [x] Test across multiple languages (Python, JavaScript, TypeScript)

**Documentation**:
- [ ] Tech debt rule reference
- [ ] Configuration examples

**Success Criteria**:
- [x] Configurable thresholds (complexity limit, file size, etc.)
- [x] Works across all supported languages
- [x] Actionable suggestions

**Implementation Notes (v2.9.4)**:
- Created 7 new rules in `claude_indexer/rules/tech_debt/`:
  - `large_files.py`: LargeFilesRule - Detects files exceeding configurable line count threshold
  - `commented_code.py`: CommentedCodeRule - Detects consecutive commented-out code blocks
  - `magic_numbers.py`: MagicNumbersRule - Detects unexplained numeric literals
  - `complexity.py`: ComplexityRule - Calculates McCabe cyclomatic complexity per function
  - `deprecated_apis.py`: DeprecatedAPIsRule - Detects deprecated stdlib usage
  - `dead_code.py`: DeadCodeRule - Detects unreachable code after return/raise/break
  - `naming_conventions.py`: NamingConventionsRule - Enforces language-specific naming conventions
- Auto-fix support for: CommentedCodeRule, DeadCodeRule, NamingConventionsRule
- Multi-language support: Python, JavaScript, TypeScript
- Comprehensive test suite: 38 tests covering all rules

---

### Milestone 2.4: Core PRD Rules (Token Drift, Duplication, Unsafe)

**Objective**: Implement the three core rules from the PRD.

#### 2.4.1 Token Drift Detection

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 2.4.1a | Design drift detection algorithm | HIGH | DONE |
| 2.4.1b | Implement code similarity tracking | HIGH | DONE |
| 2.4.1c | Create historical comparison (before/after) | HIGH | DONE |
| 2.4.1d | Add drift threshold configuration | MEDIUM | DONE |
| 2.4.1e | Generate reconciliation suggestions | MEDIUM | DONE |

**Token Drift Algorithm**:
```python
class TokenDriftRule(BaseRule):
    """Detect when similar code has diverged."""

    def check(self, context: RuleContext) -> List[Finding]:
        # 1. For each changed function/class
        # 2. Find similar entities in memory (>0.85 similarity)
        # 3. Compare implementations for drift
        # 4. Flag if drift exceeds threshold
        pass
```

#### 2.4.2 Component Duplication Detection

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 2.4.2a | Enhance existing duplicate detector | HIGH | DONE |
| 2.4.2b | Add semantic similarity (not just hash) | HIGH | DONE |
| 2.4.2c | Implement cross-file detection | HIGH | DONE |
| 2.4.2d | Add "similar but different" detection | MEDIUM | DONE |
| 2.4.2e | Generate refactoring suggestions | MEDIUM | DONE |

**Duplication Detection Levels**:
1. **Exact**: Hash match (fastest)
2. **Structural**: AST similarity >95%
3. **Semantic**: Embedding similarity >90%
4. **Behavioral**: Same inputs → same outputs (expensive, optional)

#### 2.4.3 Unsafe Structure Detection

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 2.4.3a | Define "unsafe structure" patterns | HIGH | DONE |
| 2.4.3b | Implement missing null check detection | HIGH | DONE |
| 2.4.3c | Add infinite loop risk detection | MEDIUM | DONE |
| 2.4.3d | Implement memory leak patterns | MEDIUM | DONE |
| 2.4.3e | Add concurrency issue detection | MEDIUM | DONE |

**Testing Requirements**:
- [x] Unit tests for all new rules (68 tests passing)
- [ ] Integration tests with real codebases
- [ ] Benchmark false positive rates
- [ ] Test auto-fix suggestions

**Documentation**:
- [ ] Detailed explanation of each detection type
- [ ] Configuration options
- [ ] Override mechanisms

**Success Criteria**:
- Token drift caught before commit
- Duplication detected with >90% accuracy
- Clear refactoring suggestions

**Implementation Notes (v2.9.5)**:
- Created `claude_indexer/rules/tech_debt/token_drift.py`:
  - TokenDriftRule - Detects when similar code entities have diverged
  - Uses memory search (>0.85 similarity) to find candidates
  - Compares structure, logic patterns, error handling, documentation
  - Configurable thresholds for similarity and drift detection
- Created `claude_indexer/rules/tech_debt/duplication.py`:
  - ComponentDuplicationRule - Multi-signal duplicate detection
  - Exact matching (SHA256 hash)
  - Structural matching (SimHash of AST features)
  - Semantic matching (embedding similarity via memory search)
  - Classification: EXACT, STRUCTURAL, SEMANTIC, SIMILAR
  - Generates refactoring suggestions based on duplicate type
- Created 4 resilience rules in `claude_indexer/rules/resilience/`:
  - `unsafe_null.py`: UnsafeNullRule - Detects null/None access without guards
  - `unsafe_loops.py`: UnsafeLoopRule - Detects infinite loop risks
  - `unsafe_resources.py`: UnsafeResourceRule - Detects resource leaks
  - `unsafe_concurrency.py`: UnsafeConcurrencyRule - Detects race conditions
- Multi-language support: Python, JavaScript, TypeScript
- Comprehensive test suite: 68 tests in 3 test files

---

### Milestone 2.5: Resilience & Documentation Rules (5 Rules)

**Objective**: Implement resilience and documentation checks.

#### Tasks

| ID | Task | Priority | Rule Name | Status |
|----|------|----------|-----------|--------|
| 2.5.1 | Swallowed Exception Detection | HIGH | `swallowed_exceptions` | DONE |
| 2.5.2 | Missing Timeout Detection | MEDIUM | `missing_timeout` | DONE |
| 2.5.3 | Missing Retry Logic | MEDIUM | `missing_retry` | DONE |
| 2.5.4 | Missing Docstring Detection | MEDIUM | `missing_docstring` | DONE |
| 2.5.5 | Outdated Documentation | LOW | `outdated_docs` | DONE |

**Implementation Location**: `claude_indexer/rules/resilience/` and `claude_indexer/rules/documentation/`

**Testing Requirements**:
- [x] Unit tests for each rule
- [x] Test language-specific patterns
- [x] Test configuration options

**Documentation**:
- [ ] Rule reference documentation
- [ ] Best practices guide

**Success Criteria**:
- Catches common resilience anti-patterns
- Documentation coverage metrics
- Configurable severity

**Implementation Notes (v2.9.6)**:
- Created 3 resilience rules in `claude_indexer/rules/resilience/`:
  - `swallowed_exceptions.py`: SwallowedExceptionRule - Detects empty catch blocks
  - `missing_timeout.py`: MissingTimeoutRule - Detects network calls without timeout
  - `missing_retry.py`: MissingRetryRule - Detects network operations without retry logic
- Created 2 documentation rules in `claude_indexer/rules/documentation/`:
  - `missing_docstring.py`: MissingDocstringRule - Detects undocumented functions/classes
  - `outdated_docs.py`: OutdatedDocsRule - Detects parameter/signature mismatches
- Multi-language support: Python, JavaScript, TypeScript
- Comprehensive test suite: 60+ tests in test_resilience_rules.py and test_documentation_rules.py

---

### Milestone 2.6: Git Safety Rules (3 Rules)

**Objective**: Prevent dangerous git operations.

#### Tasks

| ID | Task | Priority | Rule Name | Status |
|----|------|----------|-----------|--------|
| 2.6.1 | Force Push Detection | CRITICAL | `force_push` | DONE |
| 2.6.2 | Hard Reset Detection | CRITICAL | `hard_reset` | DONE |
| 2.6.3 | Destructive Operations | HIGH | `destructive_ops` | DONE |

**Implementation Location**: `claude_indexer/rules/git/`

**Testing Requirements**:
- [ ] Unit tests for pattern matching
- [ ] Test with various git command formats

**Documentation**:
- [ ] Override instructions
- [ ] Safe alternatives guide

**Success Criteria**:
- Zero accidental destructive operations
- Clear warnings with alternatives

---

## Phase 3: Hook System Integration

**Goal**: Integrate quality guard with Claude Code lifecycle events.

### Milestone 3.1: PostToolUse Hook (After Write)

**Objective**: Run fast checks immediately after file modifications.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 3.1.1 | Create `after-write.sh` hook script | HIGH | DONE |
| 3.1.2 | Implement fast rule filtering (<300ms rules only) | HIGH | DONE |
| 3.1.3 | Add auto-formatting integration | MEDIUM | DONE |
| 3.1.4 | Queue file for incremental indexing | HIGH | DONE |
| 3.1.5 | Implement non-blocking async mode | MEDIUM | DONE |

**Implementation Notes (v2.9.7)**:
- Created `claude_indexer/hooks/` package with:
  - `post_write.py`: PostWriteExecutor singleton for fast rule checks
  - `index_queue.py`: IndexQueue with FileChangeCoalescer for async indexing
- Added `claude-indexer post-write` CLI command (~8ms execution)
- Created `hooks/after-write.sh` shell hook integrating rules + async indexing
- Performance: <30ms typical, well under 300ms target
- Unit tests: 33 tests in `tests/unit/hooks/` (all passing)

**Hook Configuration** (`.claude/settings.json`):
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "command": ".claude/hooks/after-write.sh \"$TOOL_INPUT\""
      }
    ]
  }
}
```

**Testing Requirements**:
- [x] Test with various file types (Python, JavaScript, Markdown)
- [x] Verify <300ms execution time (achieved <30ms)
- [x] Test async indexing queue

**Documentation**:
- [x] Hook configuration guide (in CLAUDE.md)
- [x] Customization options (CLI --help)

**Success Criteria**:
- [x] <300ms latency (achieved ~8-30ms)
- [x] No blocking on indexing (async queue with debouncing)
- [x] Formatting auto-applied

---

### Milestone 3.2: Stop Hook (End of Turn)

**Objective**: Run comprehensive checks at the end of each Claude turn.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 3.2.1 | Create `end-of-turn-check.sh` hook script | HIGH | DONE |
| 3.2.2 | Implement full rule engine execution | HIGH | DONE |
| 3.2.3 | Add diff-based context (only check changes) | HIGH | DONE |
| 3.2.4 | Implement exit code 2 blocking | HIGH | DONE |
| 3.2.5 | Create structured error messages for Claude | HIGH | DONE |
| 3.2.6 | Add performance budgeting (<5s total) | MEDIUM | DONE |

**Implementation Notes (v2.9.8)**:
- Created `claude_indexer/hooks/stop_check.py`:
  - `StopCheckResult` dataclass with should_block, findings, timing
  - `StopCheckExecutor` singleton for rule engine pre-loading
  - `format_findings_for_claude()` for self-repair error messages
  - Git integration via subprocess for collecting uncommitted changes
  - Diff context population with `changed_lines` and `is_new_file`
- Added `claude-indexer stop-check` CLI command:
  - Options: `--project`, `--json`, `--timeout`, `--threshold`
  - Exit codes: 0=clean, 1=warnings, 2=BLOCKS
- Created `hooks/end-of-turn-check.sh`:
  - Shell script for Stop hook integration
  - Formats findings for Claude self-repair
  - Exit code 2 triggers blocking
- Unit tests: 30+ tests in `tests/unit/hooks/test_stop_check.py`

**Error Message Format**:
```
CRITICAL: [rule_name] - [file:line]
Description: [clear explanation]
Suggestion: [how to fix]
---
Duplicate logic detected in utils/helpers.py:42
Similar to: utils/string_ops.py:78 (92% match)
Suggestion: Use existing `normalize_string()` or refactor both to shared helper.
```

**Testing Requirements**:
- [x] Test with various violation types
- [x] Verify Claude receives and acts on errors
- [x] Benchmark total execution time

**Documentation**:
- [x] Stop hook behavior documentation (in CLAUDE.md)
- [x] Error message format specification

**Success Criteria**:
- [x] <5s total execution
- [x] Claude successfully auto-fixes flagged issues
- [x] Clear, actionable error messages

---

### Milestone 3.3: Claude Self-Repair Loop

**Objective**: Enable Claude to automatically fix detected issues.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 3.3.1 | Design error → fix workflow | HIGH | DONE |
| 3.3.2 | Implement structured error format (JSON) | HIGH | DONE |
| 3.3.3 | Create fix suggestion generator | HIGH | DONE |
| 3.3.4 | Add retry limit (prevent infinite loops) | HIGH | DONE |
| 3.3.5 | Implement escalation to user on failure | MEDIUM | DONE |

**Self-Repair Flow**:
```
1. Claude writes code
2. Stop hook detects issue, exits with code 2
3. Error message fed back to Claude
4. Claude attempts fix
5. Stop hook re-runs
6. If still failing after 3 attempts, ask user
```

**Implementation Notes (v2.9.9)**:
- Created `claude_indexer/hooks/repair_session.py`:
  - `RepairSession`: Tracks retry attempts per session (30-min TTL)
  - `RepairSessionManager`: Manages state persistence in `.claude-code-memory/`
  - Findings hash for session identification (detects same issues)
- Created `claude_indexer/hooks/fix_generator.py`:
  - `FixSuggestion`: Fix suggestions with action type and confidence
  - `FixSuggestionGenerator`: Generates suggestions from auto-fix rules
- Created `claude_indexer/hooks/repair_result.py`:
  - `RepairCheckResult`: Extended result with repair context
  - JSON serialization with repair_context and escalation fields
  - `format_for_claude()` and `format_escalation_message()` methods
- Added `--repair` flag to `claude-indexer stop-check` CLI command
- Exit codes: 0=clean, 1=warnings, 2=blocked, 3=escalated
- Updated `hooks/end-of-turn-check.sh` with repair tracking and escalation handling
- Unit tests: 59 tests in `tests/unit/hooks/` (all passing)

**Testing Requirements**:
- [x] Test auto-fix for common issues
- [x] Verify retry limit works
- [x] Test escalation flow

**Documentation**:
- [x] Self-repair behavior documented in code
- [x] CLI help updated with --repair flag

**Success Criteria**:
- Retry tracking prevents infinite loops (max 3 attempts)
- Clear escalation when needed (exit code 3)
- Fix suggestions generated for auto-fixable rules

---

### Milestone 3.4: SessionStart Hook

**Objective**: Initialize memory and verify system health at session start.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 3.4.1 | Create `session-start.sh` hook script | MEDIUM | DONE |
| 3.4.2 | Verify Qdrant connectivity | HIGH | DONE |
| 3.4.3 | Check index freshness (suggest re-index if stale) | MEDIUM | DONE |
| 3.4.4 | Load project-specific configuration | HIGH | DONE |
| 3.4.5 | Display welcome message with status | LOW | DONE |

**Implementation Notes (v2.9.13)**:
- Created `claude_indexer/hooks/session_start.py`:
  - `IndexFreshnessResult`: Tracks index staleness (time + commits)
  - `SessionStartResult`: Aggregates all health check results
  - `SessionStartExecutor`: Orchestrates health checks with graceful degradation
  - `run_session_start()`: Entry function for CLI command
- Added `claude-indexer session-start` CLI command:
  - Options: `--project`, `--collection`, `--json`, `--timeout`, `--verbose`
  - Exit codes: 0=healthy, 1=warnings (never blocks)
- Created `hooks/session-start.sh` shell wrapper:
  - Cross-platform stdin reading with timeout
  - Project root and collection name detection
  - Graceful fallback if claude-indexer not installed
- Index freshness detection:
  - Loads `_last_indexed_time` and `_last_indexed_commit` from state file
  - Stale if >24 hours old or new commits since last index
  - Actionable suggestions for re-indexing
- Unit tests: 23 tests in `tests/unit/hooks/test_session_start.py`

**Testing Requirements**:
- [x] Test with Qdrant unavailable
- [x] Test stale index detection
- [x] Test config loading

**Documentation**:
- [x] Session initialization behavior (in CLAUDE.md hooks section)
- [x] CLI command help (--help)

**Success Criteria**:
- [x] Clear indication of system health (OK/WARN/FAIL indicators)
- [x] Graceful degradation if memory unavailable
- [x] <2s startup overhead (achieved ~130ms typical)

---

## Phase 4: One-Command Onboarding

**Goal**: Enable any developer to set up the full system with a single command.

### Milestone 4.1: Init Command Implementation

**Objective**: Create `claude-indexer init` command.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 4.1.1 | Design init command flow | HIGH | DONE |
| 4.1.2 | Implement project type detection | HIGH | DONE |
| 4.1.3 | Generate `.claudeignore` from templates | HIGH | DONE |
| 4.1.4 | Generate `.claude/settings.json` with hooks | HIGH | DONE |
| 4.1.5 | Generate `guard.config.json` with defaults | HIGH | DONE |
| 4.1.6 | Create Qdrant collection for project | HIGH | DONE |
| 4.1.7 | Trigger initial indexing | HIGH | DONE |
| 4.1.8 | Install git pre-commit hook | HIGH | DONE |
| 4.1.9 | Configure MCP server connection | HIGH | DONE |
| 4.1.10 | Display summary and next steps | MEDIUM | DONE |

**Init Command Interface**:
```bash
claude-indexer init [OPTIONS]

Options:
  --project-type   Override auto-detection (python, javascript, typescript, etc.)
  --collection     Specify collection name (default: derived from project name)
  --no-index       Skip initial indexing
  --no-hooks       Skip hook installation
  --force          Overwrite existing configuration
  --verbose        Show detailed output
```

**Init Flow**:
```
1. Detect project root (look for .git, package.json, pyproject.toml, etc.)
2. Detect project type and languages used
3. Generate .claudeignore (merge with existing if present)
4. Generate .claude/settings.json
5. Generate .claude/guard.config.json
6. Install git hooks (.git/hooks/pre-commit)
7. Create Qdrant collection
8. Run initial indexing (with progress)
9. Configure MCP server
10. Display success summary
```

**Testing Requirements**:
- [x] Test on clean repository
- [x] Test on existing Claude-enabled project
- [x] Test each project type (Python, JS, TS, etc.)
- [x] Test with --force flag
- [x] Test partial failures and recovery

**Documentation**:
- [ ] Quick start guide
- [ ] Detailed init reference
- [ ] Troubleshooting guide

**Success Criteria**:
- <5 minutes from clone to fully configured
- Works for all supported project types
- Clear feedback at each step

**Implementation Notes (v2.9.10)**:
- Created `claude_indexer/init/` package with modular components:
  - `types.py`: InitOptions, InitResult, InitStepResult, ProjectType
  - `project_detector.py`: ProjectDetector for language/framework detection
  - `templates.py`: TemplateManager for variable substitution
  - `generators.py`: FileGenerator for config file creation
  - `hooks_installer.py`: HooksInstaller for Claude Code and git hooks
  - `collection_manager.py`: CollectionManager for Qdrant integration
  - `mcp_configurator.py`: MCPConfigurator for MCP server setup
  - `manager.py`: InitManager orchestrator
- Enhanced CLI with 8 options: --project, --collection, --project-type, --no-index, --no-hooks, --force, --verbose, --quiet
- Graceful degradation: continues if Qdrant unavailable or MCP not built
- Idempotent design: safe to run multiple times
- Unit tests: 49 tests in `tests/unit/init/` (all passing)

---

### Milestone 4.2: Dependency Verification

**Objective**: Ensure all dependencies are available or can be installed.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 4.2.1 | Check Python version (3.10+) | HIGH | DONE |
| 4.2.2 | Check/install Qdrant (Docker or direct) | HIGH | DONE |
| 4.2.3 | Check Claude Code CLI availability | HIGH | DONE |
| 4.2.4 | Verify API keys (OpenAI/Voyage) | MEDIUM | DONE |
| 4.2.5 | Offer to install missing components | MEDIUM | DONE |

**Verification Flow**:
```bash
claude-indexer doctor

Output:
✅ Python 3.12.0
✅ Qdrant (localhost:6333)
✅ Claude Code CLI
✅ OpenAI API key configured
⚠️  Voyage AI key not configured (optional, using OpenAI)
```

**Testing Requirements**:
- [x] Test with missing dependencies
- [x] Test auto-installation suggestions
- [x] Test on different platforms (macOS, Linux)

**Documentation**:
- [x] CLI help with usage examples
- [x] Installation suggestions for each check

**Success Criteria**:
- Clear diagnosis of missing components
- Offers suggestions on how to fix issues
- Platform-agnostic checks

**Implementation Notes (v2.9.11)**:
- Created `claude_indexer/doctor/` package with modular components:
  - `types.py`: CheckStatus, CheckCategory, CheckResult, DoctorOptions, DoctorResult
  - `checkers.py`: 8 individual check functions for Python, services, API keys, project status
  - `manager.py`: DoctorManager orchestrator with run() and run_quick() methods
- Added `claude-indexer doctor` CLI command with options:
  - `-p/--project`: Project directory to check
  - `-c/--collection`: Collection name to check
  - `--json`: JSON output format
  - `-v/--verbose`: Verbose output with details
- Exit codes: 0=pass, 1=warnings, 2=failures
- Graceful handling: Returns suggestions when checks fail
- Unit tests: 53 tests in `tests/unit/doctor/` (all passing)

---

### Milestone 4.3: Project Templates

**Objective**: Provide optimized templates for different project types.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 4.3.1 | Create Python project template | HIGH | DONE |
| 4.3.2 | Create JavaScript/Node.js template | HIGH | DONE |
| 4.3.3 | Create TypeScript template | HIGH | DONE |
| 4.3.4 | Create React/Next.js template | MEDIUM | DONE |
| 4.3.5 | Create generic template (fallback) | MEDIUM | DONE |
| 4.3.6 | Add template customization options | LOW | DONE |

**Template Contents**:
```
templates/
├── python/
│   ├── .claudeignore.template
│   └── guard.config.json.template
├── javascript/
│   ├── .claudeignore.template
│   └── guard.config.json.template
├── typescript/
│   ├── .claudeignore.template
│   └── guard.config.json.template
├── react/                             # Shared by React, Next.js, Vue
│   ├── .claudeignore.template
│   └── guard.config.json.template
└── generic/
    ├── .claudeignore.template
    └── guard.config.json.template
```

**Testing Requirements**:
- [x] Test each template generates valid config
- [x] Test template selection logic
- [x] Test customization options

**Documentation**:
- [x] Template contents documentation
- [x] Customization guide

**Success Criteria**:
- [x] Appropriate defaults for each project type
- [x] Easy to customize
- [x] All templates validated

**Implementation Notes (v2.9.12)**:
- Enhanced `TemplateManager` in `claude_indexer/init/templates.py`:
  - Added `TYPE_DIR_MAP` for project-type to template directory mapping
  - Added `_resolve_template_path()` method for project-type-aware resolution
  - Resolution order: `templates/{project_type}/{template}` → `templates/{template}`
  - Next.js and Vue share React templates (frontend patterns)
- Updated `FileGenerator` in `claude_indexer/init/generators.py`:
  - `generate_claudeignore()` now uses project-type templates
  - `generate_guard_config()` now uses project-type templates with fallback
- Created 5 template subdirectories with language-specific patterns:
  - Python: `__pycache__`, `.venv`, `.pytest_cache`, deserialization rules
  - JavaScript: `node_modules`, npm logs, XSS rules
  - TypeScript: `tsbuildinfo`, type safety rules (`@ts-ignore`, `any`)
  - React: `.next`, `.nuxt`, `.vercel`, accessibility rules
  - Generic: Minimal patterns for unknown project types
- Unit tests: 30 tests in `tests/unit/init/test_generators.py` (all passing)

---

## Phase 5: Multi-Repository Support

**Goal**: Enable concurrent usage across multiple repositories without interference.

### Milestone 5.1: Collection Isolation

**Objective**: Ensure each repository has isolated memory.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 5.1.1 | Implement collection naming scheme | HIGH | DONE |
| 5.1.2 | Add collection auto-creation on init | HIGH | DONE |
| 5.1.3 | Implement collection prefix for multi-tenancy | MEDIUM | DONE |
| 5.1.4 | Add collection listing command | MEDIUM | DONE |
| 5.1.5 | Implement collection cleanup (stale projects) | LOW | DONE |

**Collection Naming**:
```
Format: {prefix}_{project_name}_{hash}
Example: claude_avoca-next_a1b2c3

Where:
- prefix: configurable (default: "claude")
- project_name: sanitized directory name
- hash: first 6 chars of git remote URL hash (or random for non-git)
```

**Testing Requirements**:
- [x] Test collection creation
- [x] Test isolation between projects
- [x] Test cleanup of stale collections

**Documentation**:
- [x] Collection management guide (CLI --help)
- [x] Multi-tenancy setup (collection_prefix config)

**Success Criteria**:
- Zero cross-project contamination
- Deterministic naming
- Easy cleanup

**Implementation Notes (v2.9.14)**:
- Enhanced `ProjectDetector` in `claude_indexer/init/project_detector.py`:
  - `get_git_remote_url()`: Retrieves git remote origin URL
  - `get_collection_hash()`: Computes 6-char SHA256 hash from URL (or random for non-git)
  - `derive_collection_name()`: Now supports `prefix` and `include_hash` parameters
  - URL normalization: lowercase, removes `.git` suffix for consistent hashing
- Added `collection_prefix` to `IndexerConfig` in `claude_indexer/config/models.py`
- Extended `CollectionManager` in `claude_indexer/init/collection_manager.py`:
  - `list_all_collections()`: Lists all Qdrant collections
  - `list_collections_with_prefix()`: Filters collections by prefix pattern
  - `find_stale_collections()`: Identifies orphaned collections
  - `cleanup_collections()`: Removes specified collections with dry-run support
- New CLI command group `collections` in `claude_indexer/cli_full.py`:
  - `claude-indexer collections list [--filter PREFIX] [--json]`
  - `claude-indexer collections show NAME [--json]`
  - `claude-indexer collections delete NAME [--force]`
  - `claude-indexer collections cleanup [--dry-run] [--prefix PREFIX] [--force]`
- Unit tests: 14 new tests in `tests/unit/init/test_project_detector.py` and `tests/unit/test_cli.py`

---

### Milestone 5.2: Session Isolation

**Objective**: Support multiple concurrent Claude sessions on different projects.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 5.2.1 | Implement session-scoped configuration | HIGH | DONE |
| 5.2.2 | Add project detection from CWD | HIGH | DONE |
| 5.2.3 | Implement lock file for concurrent access | MEDIUM | DONE |
| 5.2.4 | Add session ID tracking | MEDIUM | DONE |
| 5.2.5 | Implement graceful handling of conflicts | MEDIUM | DONE |

**Session Isolation Architecture**:
```
Session A (Project X)          Session B (Project Y)
       │                              │
       ▼                              ▼
   Config (X)                    Config (Y)
       │                              │
       ▼                              ▼
  Collection X               Collection Y
       │                              │
       └──────────┬───────────────────┘
                  ▼
           Shared Qdrant
```

**Testing Requirements**:
- [x] Test two concurrent sessions
- [x] Test rapid session switching
- [x] Test conflict detection

**Documentation**:
- [x] Multi-session usage guide
- [x] Troubleshooting conflicts

**Success Criteria**:
- Concurrent sessions work correctly
- Clear error on conflicts
- Performance unaffected

**Implementation Notes (v2.9.15)**:
- Created `claude_indexer/session/` package with modular components:
  - `__init__.py`: Package exports (SessionContext, SessionManager, LockManager, etc.)
  - `detector.py`: ProjectRootDetector for CWD-based project root detection
  - `context.py`: SessionContext dataclass with session state tracking
  - `lock.py`: LockManager using fcntl.flock() for file-based locking
  - `manager.py`: SessionManager orchestrator for session lifecycle
- Session ID format: `{hostname}_{timestamp}_{random}` (e.g., "mbp_1702401234_a3f2")
- Lock file format: JSON with session_id, pid, hostname, acquired_at
- Session file persistence in `.claude-indexer/session.json`
- TTL-based session expiration (24 hours) with auto-cleanup
- Integrated SessionManager into `session_start.py` for welcome message
- Added `session` CLI command group with 3 subcommands:
  - `session info`: Show current session information
  - `session clear`: Clear session state for a project
  - `session list`: List all known sessions
- Unit tests: 70 tests in `tests/unit/session/` (all passing)
- LockConflictError exception for graceful conflict handling

---

### Milestone 5.3: Workspace Support

**Objective**: Support VS Code multi-root workspaces and monorepos.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 5.3.1 | Detect multi-root workspace | MEDIUM | DONE |
| 5.3.2 | Implement per-folder configuration | MEDIUM | DONE |
| 5.3.3 | Add monorepo support (single collection, multiple paths) | MEDIUM | DONE |
| 5.3.4 | Implement workspace-level settings | LOW | DONE |

**Testing Requirements**:
- [x] Test with VS Code workspace
- [x] Test monorepo indexing
- [x] Test per-folder rules

**Documentation**:
- [x] Workspace setup guide (CLI --help)
- [x] Monorepo best practices (collection strategy docs)

**Success Criteria**:
- [x] Multi-root workspaces work seamlessly
- [x] Monorepo support for large projects
- [x] Clear per-folder configuration

**Implementation Notes (v2.9.16)**:
- Created `claude_indexer/workspace/` package with modular components:
  - `types.py`: WorkspaceType enum (8 types), CollectionStrategy, WorkspaceMember, WorkspaceConfig
  - `detector.py`: WorkspaceDetector with priority-based marker detection
  - `config.py`: WorkspaceConfigLoader for hierarchical config merging
  - `context.py`: WorkspaceContext for session state tracking
  - `manager.py`: WorkspaceManager orchestrator with convenience functions
- Workspace type detection priority:
  1. VS Code multi-root (*.code-workspace) → MULTIPLE collections
  2. pnpm (pnpm-workspace.yaml) → SINGLE collection
  3. Nx (nx.json) → SINGLE collection
  4. Lerna (lerna.json) → SINGLE collection
  5. Turborepo (turbo.json) → SINGLE collection
  6. npm/yarn workspaces (package.json) → SINGLE collection
- Collection strategy rationale:
  - Monorepos → SINGLE collection (cross-package semantic search)
  - VS Code multi-root → MULTIPLE collections (folders often unrelated)
- New CLI command group `workspace` in `claude_indexer/cli_full.py`:
  - `claude-indexer workspace detect [-p PATH] [--json]`
  - `claude-indexer workspace init [-p PATH] [--strategy]`
  - `claude-indexer workspace status [-p PATH] [--json]`
  - `claude-indexer workspace clear [-p PATH]`
- Session state persistence in `.claude-indexer/workspace.json`
- Unit tests: 87 tests in `tests/unit/workspace/` (all passing)

---

## Phase 6: Polish & Optimization

**Goal**: Optimize performance, enhance UX, and ensure production readiness.

### Milestone 6.1: Performance Optimization

**Objective**: Meet all performance targets from PRD.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 6.1.1 | Profile end-to-end latency | HIGH | DONE |
| 6.1.2 | Optimize embedding batching | HIGH | DONE |
| 6.1.3 | Add query result caching | MEDIUM | DONE |
| 6.1.4 | Implement parallel rule execution | MEDIUM | DONE |
| 6.1.5 | Add lazy loading for expensive operations | MEDIUM | DONE |
| 6.1.6 | Create performance dashboard | LOW | DONE |

**Implementation Notes (v2.9.17)**:
- Created `claude_indexer/performance/` package with modular components:
  - `timing.py`: Existing `@timed` decorator, `PerformanceTimer`, `PerformanceAggregator`
  - `profiler.py`: `EndToEndProfiler` with nested `section()` support, `ProfileResult`, `ProfilerStack`
  - `metrics.py`: `PerformanceMetricsCollector` singleton with p50/p95/p99 percentiles, time-windowed stats
- Created `claude_indexer/storage/query_cache.py`:
  - `QueryResultCache` LRU cache with TTL expiration (default 60s)
  - Integrated into `QdrantStore.search_similar()` with `enable_query_cache` option
  - Automatic invalidation on `delete_collection()`
- Created `claude_indexer/utils/lazy.py`:
  - `lazy_property` decorator for thread-safe lazy initialization
  - `lazy_init` decorator for cached function results with timing callback
  - `LazyModule` for deferred module imports
- Modified `claude_indexer/rules/engine.py`:
  - Added `_execute_rules_parallel()` using `ThreadPoolExecutor`
  - Configurable `max_parallel_workers` and `parallel_rule_timeout_ms`
  - Sequential fallback for single rule or disabled config
- Created `BatchingEmbedder` in `claude_indexer/embeddings/base.py`:
  - Wraps embedder with `BatchOptimizer` for memory-aware adaptive sizing
  - Records `BatchMetrics` for optimization feedback
- Added CLI commands `claude-indexer perf {show,export,clear,cache-stats}`:
  - `perf show`: Display metrics with optional JSON format
  - `perf export`: Export metrics to file
  - `perf clear`: Clear metrics for operation or all
  - `perf cache-stats`: Show query cache statistics
- Environment variable `CLAUDE_INDEXER_PROFILE=1` enables profiling
- Unit tests: 70 tests in `tests/unit/performance/`, `tests/unit/storage/test_query_cache.py`, `tests/unit/utils/test_lazy.py`, `tests/unit/rules/test_parallel_execution.py`

**Performance Targets**:
| Operation | Target | Current |
|-----------|--------|---------|
| After-write hook | <300ms | ~200ms |
| End-of-turn check | <5s | ~3s |
| Semantic search | <200ms | ~150ms |
| Metadata search | <50ms | ~10ms |
| Initial index (1000 files) | <2min | ~3min |
| Incremental index (1 file) | <1s | ~500ms |

**Testing Requirements**:
- [ ] Benchmark all operations
- [ ] Test under load (many files)
- [ ] Test with slow network (cloud Qdrant)

**Documentation**:
- [ ] Performance tuning guide
- [ ] Benchmarking methodology

**Success Criteria**:
- All targets met
- No performance regression
- Clear metrics

---

### Milestone 6.2: User Experience Polish

**Objective**: Ensure the "magical" UX described in PRD.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 6.2.1 | Improve error messages (actionable, clear) | HIGH | PARTIAL |
| 6.2.2 | Add progress indicators for long operations | MEDIUM | PARTIAL |
| 6.2.3 | Implement quiet mode (minimal output) | MEDIUM | NEW |
| 6.2.4 | Add verbose mode (debugging) | MEDIUM | DONE |
| 6.2.5 | Create status command for system health | MEDIUM | PARTIAL |
| 6.2.6 | Add color output with accessibility options | LOW | NEW |

**Testing Requirements**:
- [ ] User testing with developers
- [ ] Test error message clarity
- [ ] Test quiet/verbose modes

**Documentation**:
- [ ] UX guidelines for contributors
- [ ] Accessibility documentation

**Success Criteria**:
- Users feel it "just works"
- Errors are self-explanatory
- No unnecessary output

---

### Milestone 6.3: Documentation Complete

**Objective**: Comprehensive documentation for all users.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 6.3.1 | Update README.md with quick start | HIGH | PARTIAL |
| 6.3.2 | Complete CLI_REFERENCE.md | HIGH | PARTIAL |
| 6.3.3 | Complete MEMORY_GUARD.md (all 27 rules) | HIGH | PARTIAL |
| 6.3.4 | Create TROUBLESHOOTING.md | MEDIUM | NEW |
| 6.3.5 | Create ARCHITECTURE.md diagrams | MEDIUM | PARTIAL |
| 6.3.6 | Add inline code documentation | MEDIUM | PARTIAL |
| 6.3.7 | Create video tutorials (optional) | LOW | NEW |

**Documentation Structure**:
```
docs/
├── QUICK_START.md          # 5-minute setup
├── CLI_REFERENCE.md        # All commands
├── CONFIGURATION.md        # All config options
├── MEMORY_GUARD.md         # All 27 rules
├── HOOKS.md                # Hook system
├── RULE_AUTHORING.md       # Creating custom rules
├── TROUBLESHOOTING.md      # Common issues
├── ARCHITECTURE.md         # System design
└── API_REFERENCE.md        # MCP tools reference
```

**Testing Requirements**:
- [ ] Test all commands in docs work
- [ ] Review for accuracy
- [ ] Check for broken links

**Success Criteria**:
- New user can start in <5 minutes
- All features documented
- No outdated information

---

### Milestone 6.4: Test Coverage Complete

**Objective**: Comprehensive test coverage for reliability.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 6.4.1 | Achieve >80% unit test coverage | HIGH | PARTIAL |
| 6.4.2 | Add integration tests for all commands | HIGH | PARTIAL |
| 6.4.3 | Add end-to-end tests (init → use → commit) | HIGH | NEW |
| 6.4.4 | Add performance regression tests | MEDIUM | NEW |
| 6.4.5 | Add cross-platform tests | MEDIUM | NEW |
| 6.4.6 | Set up CI pipeline | MEDIUM | PARTIAL |

**Test Organization**:
```
tests/
├── unit/                   # Fast, isolated tests
│   ├── test_config.py
│   ├── test_rules/
│   │   ├── test_security_rules.py
│   │   ├── test_tech_debt_rules.py
│   │   └── ...
│   ├── test_indexing.py
│   └── test_search.py
├── integration/            # Tests with real services
│   ├── test_init_command.py
│   ├── test_hook_execution.py
│   └── test_qdrant_integration.py
└── e2e/                    # Full workflow tests
    ├── test_new_project_workflow.py
    └── test_self_repair_loop.py
```

**Testing Requirements**:
- [ ] >80% coverage
- [ ] All critical paths tested
- [ ] CI runs on every PR

**Success Criteria**:
- High confidence in releases
- Fast feedback on regressions
- Clear test reports

---

## Appendix: Rule Specifications

### A.1 Security Rules (11)

| # | Rule | Severity | Pattern | Auto-Fix |
|---|------|----------|---------|----------|
| 1 | `sql_injection` | CRITICAL | Raw SQL with string concat | No |
| 2 | `xss_vulnerability` | CRITICAL | Unescaped HTML output | No |
| 3 | `command_injection` | CRITICAL | Shell exec with user input | No |
| 4 | `hardcoded_secrets` | CRITICAL | API keys, passwords in code | No |
| 5 | `insecure_crypto` | HIGH | MD5, SHA1 for security | No |
| 6 | `path_traversal` | HIGH | File paths with user input | No |
| 7 | `insecure_deserialize` | HIGH | pickle, eval with untrusted | No |
| 8 | `missing_auth` | HIGH | Routes without auth checks | No |
| 9 | `sensitive_exposure` | MEDIUM | Logging sensitive data | Yes |
| 10 | `insecure_random` | MEDIUM | Math.random for security | Yes |
| 11 | `missing_https` | MEDIUM | HTTP URLs for APIs | Yes |

### A.2 Tech Debt Rules (9)

| # | Rule | Severity | Pattern | Auto-Fix |
|---|------|----------|---------|----------|
| 1 | `todo_markers` | MEDIUM | TODO, FIXME, HACK comments | No |
| 2 | `debug_statements` | MEDIUM | console.log, print debug | Yes |
| 3 | `commented_code` | LOW | Large commented blocks | Yes |
| 4 | `dead_code` | MEDIUM | Unreachable code | Yes |
| 5 | `complexity` | MEDIUM | Cyclomatic complexity >10 | No |
| 6 | `large_files` | LOW | Files >500 lines | No |
| 7 | `magic_numbers` | LOW | Unexplained numeric literals | No |
| 8 | `naming_conventions` | MEDIUM | Inconsistent naming | Yes |
| 9 | `deprecated_apis` | MEDIUM | Using deprecated functions | No |

### A.3 Resilience Rules (3)

| # | Rule | Severity | Pattern | Auto-Fix |
|---|------|----------|---------|----------|
| 1 | `swallowed_exceptions` | HIGH | Empty catch blocks | No |
| 2 | `missing_timeout` | MEDIUM | Network calls without timeout | No |
| 3 | `missing_retry` | MEDIUM | Critical ops without retry | No |

### A.4 Documentation Rules (2)

| # | Rule | Severity | Pattern | Auto-Fix |
|---|------|----------|---------|----------|
| 1 | `missing_docstring` | MEDIUM | Public functions without docs | No |
| 2 | `outdated_docs` | LOW | Docs don't match signature | No |

### A.5 Git Safety Rules (3)

| # | Rule | Severity | Pattern | Auto-Fix |
|---|------|----------|---------|----------|
| 1 | `force_push` | CRITICAL | git push --force | No |
| 2 | `hard_reset` | CRITICAL | git reset --hard | No |
| 3 | `destructive_ops` | HIGH | rm -rf, etc. | No |

---

## Implementation Order Summary

### Critical Path (Must Have)

1. **Phase 0**: Configuration system, .claudeignore, logging
2. **Phase 1**: Indexing pipeline, incremental updates, memory queries
3. **Phase 2**: Rule engine, core PRD rules (drift, duplication, unsafe)
4. **Phase 3**: Hook integration, self-repair loop
5. **Phase 4**: One-command init

### High Priority (Should Have)

6. **Phase 2 (continued)**: All 27 rules
7. **Phase 5**: Multi-repo isolation
8. **Phase 6**: Performance optimization, documentation

### Lower Priority (Nice to Have)

9. **Phase 5 (continued)**: Workspace/monorepo support
10. **Phase 6 (continued)**: Polish, video tutorials

---

## Dependencies Graph

```
Phase 0 ────┬─────► Phase 1 ────┬─────► Phase 3
            │                   │
            │                   ▼
            │              Phase 2 ────► Phase 3
            │                   │
            ▼                   ▼
       Phase 4 ◄───────────────┘
            │
            ▼
       Phase 5
            │
            ▼
       Phase 6
```

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Qdrant unavailable | HIGH | Graceful degradation, clear errors |
| False positives annoying | HIGH | Configurable thresholds, overrides |
| Performance too slow | MEDIUM | Async operations, caching |
| Complex setup fails | HIGH | Doctor command, detailed errors |
| Cross-project contamination | HIGH | Strong isolation, testing |

---

## Success Criteria Summary

- [ ] New project setup: <5 minutes
- [ ] End-of-turn checks: <5 seconds
- [ ] User interruption rate: <10%
- [ ] Critical issues blocked: >95%
- [ ] Test coverage: >80%
- [ ] All 27 rules implemented
- [ ] Multi-repo works correctly
- [ ] Documentation complete

---

*Generated from PRD.md and TDD.md analysis*
