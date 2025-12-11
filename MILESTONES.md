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

### Current State (60-70% Complete)
| Component | Status | Notes |
|-----------|--------|-------|
| CLI Infrastructure | ✅ Complete | `claude-indexer` with 20+ commands |
| Qdrant Integration | ✅ Complete | Hybrid search (semantic + BM25) |
| MCP Server | ✅ Complete | 8+ tools, streaming responses |
| Hook Framework | ✅ Complete | PreToolUse, Stop, SessionStart |
| UI Consistency | ✅ Complete | 15+ rules, 3-tier architecture |
| Memory Guard v4.3 | ✅ Complete | 21+ pattern checks |
| Multi-language Parser | ✅ Complete | 7 languages supported |
| One-Command Init | ❌ Missing | Core gap |
| Full Indexing Pipeline | 🔄 Partial | Incremental needs work |
| All 27 Rules | 🔄 Partial | ~15 implemented |
| Multi-Repo Isolation | 🔄 Partial | Framework exists |
| Claude Self-Repair Loop | 🔄 Partial | Needs tighter integration |

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
| 0.2.1 | Create `.claudeignore` parser (gitignore-compatible) | HIGH | NEW |
| 0.2.2 | Integrate with indexer (skip ignored files) | HIGH | PARTIAL |
| 0.2.3 | Integrate with MCP server (filter search results) | HIGH | NEW |
| 0.2.4 | Create default `.claudeignore` template | MEDIUM | NEW |
| 0.2.5 | Add CLI command: `claude-indexer ignore [pattern]` | LOW | NEW |
| 0.2.6 | Implement hierarchical ignore (global + project) | MEDIUM | NEW |

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
- [ ] Unit tests for pattern matching
- [ ] Integration tests with indexer
- [ ] Test inheritance (global + project)

**Documentation**:
- [ ] `.claudeignore` format specification
- [ ] Common patterns for different project types

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
| 0.3.1 | Create unified logging module (`claude_indexer/logging.py`) | HIGH | NEW |
| 0.3.2 | Implement log rotation (3-file, size-based) | MEDIUM | PARTIAL |
| 0.3.3 | Add structured logging (JSON format option) | MEDIUM | NEW |
| 0.3.4 | Create debug mode with verbose output | HIGH | PARTIAL |
| 0.3.5 | Add performance timing decorators | MEDIUM | NEW |
| 0.3.6 | Implement log aggregation for multi-component debugging | LOW | NEW |

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
- [ ] Verify log rotation works correctly
- [ ] Test debug mode activation
- [ ] Ensure no sensitive data in logs

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
| 1.1.1 | Create `IndexingPipeline` class in `claude_indexer/indexing/pipeline.py` | HIGH | NEW |
| 1.1.2 | Implement parallel file processing (thread pool) | HIGH | PARTIAL |
| 1.1.3 | Add intelligent chunking (function/class boundaries) | HIGH | DONE |
| 1.1.4 | Implement embedding batching (reduce API calls) | HIGH | PARTIAL |
| 1.1.5 | Create progress reporter with ETA | MEDIUM | NEW |
| 1.1.6 | Add resume capability for interrupted indexing | MEDIUM | NEW |
| 1.1.7 | Implement file hash caching (skip unchanged) | HIGH | PARTIAL |

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
- [ ] Unit tests for each component
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

---

### Milestone 1.2: Incremental Indexing (Git-Aware)

**Objective**: Efficiently update index when files change.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 1.2.1 | Create `GitChangeDetector` class | HIGH | NEW |
| 1.2.2 | Implement `get_changed_files(since_commit)` | HIGH | NEW |
| 1.2.3 | Add file hash comparison fallback (non-git repos) | MEDIUM | NEW |
| 1.2.4 | Create batch update processor | HIGH | PARTIAL |
| 1.2.5 | Handle file deletions (remove from index) | HIGH | NEW |
| 1.2.6 | Handle file renames (preserve history) | MEDIUM | NEW |
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
- [ ] Test with various git operations (commit, merge, rebase, checkout)
- [ ] Test non-git repository fallback
- [ ] Test file rename tracking

**Documentation**:
- [ ] Document git integration behavior
- [ ] Troubleshooting for git-related issues

**Success Criteria**:
- Incremental update <1s for single file
- Correct handling of all git operations
- Non-git repos still work via hash comparison

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
| 2.1.3 | Implement rule discovery (auto-load from directory) | HIGH | NEW |
| 2.1.4 | Add rule configuration (enable/disable, thresholds) | HIGH | NEW |
| 2.1.5 | Create `RuleContext` with diff, memory access | HIGH | PARTIAL |
| 2.1.6 | Implement severity levels (CRITICAL, HIGH, MEDIUM, LOW) | HIGH | DONE |
| 2.1.7 | Add auto-fix capability to rule interface | MEDIUM | NEW |

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
- [ ] Unit tests for rule engine
- [ ] Test rule discovery mechanism
- [ ] Test severity filtering

**Documentation**:
- [ ] Rule authoring guide in `docs/RULE_AUTHORING.md`
- [ ] Rule configuration reference

**Success Criteria**:
- New rules can be added without code changes
- Rules configurable via JSON
- Clear finding messages

---

### Milestone 2.2: Security Rules (11 Rules)

**Objective**: Implement all security-focused quality checks.

#### Tasks

| ID | Task | Priority | Rule Name | Status |
|----|------|----------|-----------|--------|
| 2.2.1 | SQL Injection Detection | CRITICAL | `sql_injection` | PARTIAL |
| 2.2.2 | XSS Detection | CRITICAL | `xss_vulnerability` | PARTIAL |
| 2.2.3 | Command Injection Detection | CRITICAL | `command_injection` | NEW |
| 2.2.4 | Hardcoded Secrets Detection | CRITICAL | `hardcoded_secrets` | PARTIAL |
| 2.2.5 | Insecure Crypto Detection | HIGH | `insecure_crypto` | NEW |
| 2.2.6 | Path Traversal Detection | HIGH | `path_traversal` | NEW |
| 2.2.7 | Insecure Deserialization | HIGH | `insecure_deserialize` | NEW |
| 2.2.8 | Missing Authentication | HIGH | `missing_auth` | NEW |
| 2.2.9 | Sensitive Data Exposure | MEDIUM | `sensitive_exposure` | PARTIAL |
| 2.2.10 | Insecure Random | MEDIUM | `insecure_random` | NEW |
| 2.2.11 | Missing HTTPS | MEDIUM | `missing_https` | NEW |

**Implementation Location**: `claude_indexer/rules/security/`

**Testing Requirements**:
- [ ] Unit tests for each rule with positive/negative cases
- [ ] Test with real-world vulnerable code samples
- [ ] False positive rate <5%

**Documentation**:
- [ ] Security rule reference in `docs/MEMORY_GUARD.md`
- [ ] Examples of detected patterns

**Success Criteria**:
- All OWASP Top 10 covered
- <5% false positive rate
- Clear remediation guidance

---

### Milestone 2.3: Tech Debt Rules (9 Rules)

**Objective**: Implement technical debt detection rules.

#### Tasks

| ID | Task | Priority | Rule Name | Status |
|----|------|----------|-----------|--------|
| 2.3.1 | TODO/FIXME/HACK Detection | MEDIUM | `todo_markers` | DONE |
| 2.3.2 | Debug Statement Detection | MEDIUM | `debug_statements` | DONE |
| 2.3.3 | Commented Code Detection | LOW | `commented_code` | PARTIAL |
| 2.3.4 | Dead Code Detection | MEDIUM | `dead_code` | NEW |
| 2.3.5 | Overly Complex Functions | MEDIUM | `complexity` | NEW |
| 2.3.6 | Large Files Detection | LOW | `large_files` | NEW |
| 2.3.7 | Magic Numbers Detection | LOW | `magic_numbers` | NEW |
| 2.3.8 | Inconsistent Naming | MEDIUM | `naming_conventions` | NEW |
| 2.3.9 | Deprecated API Usage | MEDIUM | `deprecated_apis` | NEW |

**Implementation Location**: `claude_indexer/rules/tech_debt/`

**Testing Requirements**:
- [ ] Unit tests for each rule
- [ ] Test threshold configurations
- [ ] Test across multiple languages

**Documentation**:
- [ ] Tech debt rule reference
- [ ] Configuration examples

**Success Criteria**:
- Configurable thresholds (complexity limit, file size, etc.)
- Works across all supported languages
- Actionable suggestions

---

### Milestone 2.4: Core PRD Rules (Token Drift, Duplication, Unsafe)

**Objective**: Implement the three core rules from the PRD.

#### 2.4.1 Token Drift Detection

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 2.4.1a | Design drift detection algorithm | HIGH | NEW |
| 2.4.1b | Implement code similarity tracking | HIGH | NEW |
| 2.4.1c | Create historical comparison (before/after) | HIGH | NEW |
| 2.4.1d | Add drift threshold configuration | MEDIUM | NEW |
| 2.4.1e | Generate reconciliation suggestions | MEDIUM | NEW |

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
| 2.4.2a | Enhance existing duplicate detector | HIGH | PARTIAL |
| 2.4.2b | Add semantic similarity (not just hash) | HIGH | PARTIAL |
| 2.4.2c | Implement cross-file detection | HIGH | NEW |
| 2.4.2d | Add "similar but different" detection | MEDIUM | NEW |
| 2.4.2e | Generate refactoring suggestions | MEDIUM | NEW |

**Duplication Detection Levels**:
1. **Exact**: Hash match (fastest)
2. **Structural**: AST similarity >95%
3. **Semantic**: Embedding similarity >90%
4. **Behavioral**: Same inputs → same outputs (expensive, optional)

#### 2.4.3 Unsafe Structure Detection

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 2.4.3a | Define "unsafe structure" patterns | HIGH | NEW |
| 2.4.3b | Implement missing null check detection | HIGH | NEW |
| 2.4.3c | Add infinite loop risk detection | MEDIUM | NEW |
| 2.4.3d | Implement memory leak patterns | MEDIUM | NEW |
| 2.4.3e | Add concurrency issue detection | MEDIUM | NEW |

**Testing Requirements**:
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

---

### Milestone 2.5: Resilience & Documentation Rules (5 Rules)

**Objective**: Implement resilience and documentation checks.

#### Tasks

| ID | Task | Priority | Rule Name | Status |
|----|------|----------|-----------|--------|
| 2.5.1 | Swallowed Exception Detection | HIGH | `swallowed_exceptions` | PARTIAL |
| 2.5.2 | Missing Timeout Detection | MEDIUM | `missing_timeout` | PARTIAL |
| 2.5.3 | Missing Retry Logic | MEDIUM | `missing_retry` | NEW |
| 2.5.4 | Missing Docstring Detection | MEDIUM | `missing_docstring` | PARTIAL |
| 2.5.5 | Outdated Documentation | LOW | `outdated_docs` | NEW |

**Implementation Location**: `claude_indexer/rules/resilience/` and `claude_indexer/rules/documentation/`

**Testing Requirements**:
- [ ] Unit tests for each rule
- [ ] Test language-specific patterns
- [ ] Test configuration options

**Documentation**:
- [ ] Rule reference documentation
- [ ] Best practices guide

**Success Criteria**:
- Catches common resilience anti-patterns
- Documentation coverage metrics
- Configurable severity

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
| 3.1.1 | Create `after-write.sh` hook script | HIGH | PARTIAL |
| 3.1.2 | Implement fast rule filtering (<300ms rules only) | HIGH | PARTIAL |
| 3.1.3 | Add auto-formatting integration | MEDIUM | DONE |
| 3.1.4 | Queue file for incremental indexing | HIGH | NEW |
| 3.1.5 | Implement non-blocking async mode | MEDIUM | NEW |

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
- [ ] Test with various file types
- [ ] Verify <300ms execution time
- [ ] Test async indexing queue

**Documentation**:
- [ ] Hook configuration guide
- [ ] Customization options

**Success Criteria**:
- <300ms latency
- No blocking on indexing
- Formatting auto-applied

---

### Milestone 3.2: Stop Hook (End of Turn)

**Objective**: Run comprehensive checks at the end of each Claude turn.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 3.2.1 | Create `end-of-turn-check.sh` hook script | HIGH | PARTIAL |
| 3.2.2 | Implement full rule engine execution | HIGH | PARTIAL |
| 3.2.3 | Add diff-based context (only check changes) | HIGH | PARTIAL |
| 3.2.4 | Implement exit code 2 blocking | HIGH | DONE |
| 3.2.5 | Create structured error messages for Claude | HIGH | PARTIAL |
| 3.2.6 | Add performance budgeting (<5s total) | MEDIUM | NEW |

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
- [ ] Test with various violation types
- [ ] Verify Claude receives and acts on errors
- [ ] Benchmark total execution time

**Documentation**:
- [ ] Stop hook behavior documentation
- [ ] Error message format specification

**Success Criteria**:
- <5s total execution
- Claude successfully auto-fixes flagged issues
- Clear, actionable error messages

---

### Milestone 3.3: Claude Self-Repair Loop

**Objective**: Enable Claude to automatically fix detected issues.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 3.3.1 | Design error → fix workflow | HIGH | NEW |
| 3.3.2 | Implement structured error format (JSON) | HIGH | PARTIAL |
| 3.3.3 | Create fix suggestion generator | HIGH | NEW |
| 3.3.4 | Add retry limit (prevent infinite loops) | HIGH | NEW |
| 3.3.5 | Implement escalation to user on failure | MEDIUM | NEW |

**Self-Repair Flow**:
```
1. Claude writes code
2. Stop hook detects issue, exits with code 2
3. Error message fed back to Claude
4. Claude attempts fix
5. Stop hook re-runs
6. If still failing after 3 attempts, ask user
```

**Testing Requirements**:
- [ ] Test auto-fix for common issues
- [ ] Verify retry limit works
- [ ] Test escalation flow

**Documentation**:
- [ ] Self-repair behavior documentation
- [ ] Customization options

**Success Criteria**:
- >80% of flagged issues auto-fixed
- No infinite loops
- Clear escalation when needed

---

### Milestone 3.4: SessionStart Hook

**Objective**: Initialize memory and verify system health at session start.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 3.4.1 | Create `session-start.sh` hook script | MEDIUM | PARTIAL |
| 3.4.2 | Verify Qdrant connectivity | HIGH | PARTIAL |
| 3.4.3 | Check index freshness (suggest re-index if stale) | MEDIUM | NEW |
| 3.4.4 | Load project-specific configuration | HIGH | PARTIAL |
| 3.4.5 | Display welcome message with status | LOW | NEW |

**Testing Requirements**:
- [ ] Test with Qdrant unavailable
- [ ] Test stale index detection
- [ ] Test config loading

**Documentation**:
- [ ] Session initialization behavior
- [ ] Troubleshooting connectivity issues

**Success Criteria**:
- Clear indication of system health
- Graceful degradation if memory unavailable
- <2s startup overhead

---

## Phase 4: One-Command Onboarding

**Goal**: Enable any developer to set up the full system with a single command.

### Milestone 4.1: Init Command Implementation

**Objective**: Create `claude-indexer init` command.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 4.1.1 | Design init command flow | HIGH | NEW |
| 4.1.2 | Implement project type detection | HIGH | NEW |
| 4.1.3 | Generate `.claudeignore` from templates | HIGH | NEW |
| 4.1.4 | Generate `.claude/settings.json` with hooks | HIGH | NEW |
| 4.1.5 | Generate `guard.config.json` with defaults | HIGH | NEW |
| 4.1.6 | Create Qdrant collection for project | HIGH | NEW |
| 4.1.7 | Trigger initial indexing | HIGH | NEW |
| 4.1.8 | Install git pre-commit hook | HIGH | NEW |
| 4.1.9 | Configure MCP server connection | HIGH | NEW |
| 4.1.10 | Display summary and next steps | MEDIUM | NEW |

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
- [ ] Test on clean repository
- [ ] Test on existing Claude-enabled project
- [ ] Test each project type (Python, JS, TS, etc.)
- [ ] Test with --force flag
- [ ] Test partial failures and recovery

**Documentation**:
- [ ] Quick start guide
- [ ] Detailed init reference
- [ ] Troubleshooting guide

**Success Criteria**:
- <5 minutes from clone to fully configured
- Works for all supported project types
- Clear feedback at each step

---

### Milestone 4.2: Dependency Verification

**Objective**: Ensure all dependencies are available or can be installed.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 4.2.1 | Check Python version (3.10+) | HIGH | NEW |
| 4.2.2 | Check/install Qdrant (Docker or direct) | HIGH | NEW |
| 4.2.3 | Check Claude Code CLI availability | HIGH | NEW |
| 4.2.4 | Verify API keys (OpenAI/Voyage) | MEDIUM | NEW |
| 4.2.5 | Offer to install missing components | MEDIUM | NEW |

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
- [ ] Test with missing dependencies
- [ ] Test auto-installation offers
- [ ] Test on different platforms (macOS, Linux)

**Documentation**:
- [ ] Dependency requirements
- [ ] Manual installation guides
- [ ] Platform-specific notes

**Success Criteria**:
- Clear diagnosis of missing components
- Offers to fix what it can
- Platform-agnostic checks

---

### Milestone 4.3: Project Templates

**Objective**: Provide optimized templates for different project types.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 4.3.1 | Create Python project template | HIGH | NEW |
| 4.3.2 | Create JavaScript/Node.js template | HIGH | NEW |
| 4.3.3 | Create TypeScript template | HIGH | NEW |
| 4.3.4 | Create React/Next.js template | MEDIUM | NEW |
| 4.3.5 | Create generic template (fallback) | MEDIUM | NEW |
| 4.3.6 | Add template customization options | LOW | NEW |

**Template Contents**:
```
templates/
├── python/
│   ├── .claudeignore
│   ├── guard.config.json
│   └── settings.json
├── javascript/
│   ├── .claudeignore
│   ├── guard.config.json
│   └── settings.json
├── typescript/
│   └── ...
└── generic/
    └── ...
```

**Testing Requirements**:
- [ ] Test each template generates valid config
- [ ] Test template selection logic
- [ ] Test customization options

**Documentation**:
- [ ] Template contents documentation
- [ ] Customization guide

**Success Criteria**:
- Appropriate defaults for each project type
- Easy to customize
- All templates validated

---

## Phase 5: Multi-Repository Support

**Goal**: Enable concurrent usage across multiple repositories without interference.

### Milestone 5.1: Collection Isolation

**Objective**: Ensure each repository has isolated memory.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 5.1.1 | Implement collection naming scheme | HIGH | PARTIAL |
| 5.1.2 | Add collection auto-creation on init | HIGH | PARTIAL |
| 5.1.3 | Implement collection prefix for multi-tenancy | MEDIUM | NEW |
| 5.1.4 | Add collection listing command | MEDIUM | NEW |
| 5.1.5 | Implement collection cleanup (stale projects) | LOW | NEW |

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
- [ ] Test collection creation
- [ ] Test isolation between projects
- [ ] Test cleanup of stale collections

**Documentation**:
- [ ] Collection management guide
- [ ] Multi-tenancy setup

**Success Criteria**:
- Zero cross-project contamination
- Deterministic naming
- Easy cleanup

---

### Milestone 5.2: Session Isolation

**Objective**: Support multiple concurrent Claude sessions on different projects.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 5.2.1 | Implement session-scoped configuration | HIGH | NEW |
| 5.2.2 | Add project detection from CWD | HIGH | PARTIAL |
| 5.2.3 | Implement lock file for concurrent access | MEDIUM | NEW |
| 5.2.4 | Add session ID tracking | MEDIUM | NEW |
| 5.2.5 | Implement graceful handling of conflicts | MEDIUM | NEW |

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
- [ ] Test two concurrent sessions
- [ ] Test rapid session switching
- [ ] Test conflict detection

**Documentation**:
- [ ] Multi-session usage guide
- [ ] Troubleshooting conflicts

**Success Criteria**:
- Concurrent sessions work correctly
- Clear error on conflicts
- Performance unaffected

---

### Milestone 5.3: Workspace Support

**Objective**: Support VS Code multi-root workspaces and monorepos.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 5.3.1 | Detect multi-root workspace | MEDIUM | NEW |
| 5.3.2 | Implement per-folder configuration | MEDIUM | NEW |
| 5.3.3 | Add monorepo support (single collection, multiple paths) | MEDIUM | NEW |
| 5.3.4 | Implement workspace-level settings | LOW | NEW |

**Testing Requirements**:
- [ ] Test with VS Code workspace
- [ ] Test monorepo indexing
- [ ] Test per-folder rules

**Documentation**:
- [ ] Workspace setup guide
- [ ] Monorepo best practices

**Success Criteria**:
- Multi-root workspaces work seamlessly
- Monorepo support for large projects
- Clear per-folder configuration

---

## Phase 6: Polish & Optimization

**Goal**: Optimize performance, enhance UX, and ensure production readiness.

### Milestone 6.1: Performance Optimization

**Objective**: Meet all performance targets from PRD.

#### Tasks

| ID | Task | Priority | Status |
|----|------|----------|--------|
| 6.1.1 | Profile end-to-end latency | HIGH | NEW |
| 6.1.2 | Optimize embedding batching | HIGH | PARTIAL |
| 6.1.3 | Add query result caching | MEDIUM | NEW |
| 6.1.4 | Implement parallel rule execution | MEDIUM | NEW |
| 6.1.5 | Add lazy loading for expensive operations | MEDIUM | PARTIAL |
| 6.1.6 | Create performance dashboard | LOW | NEW |

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
