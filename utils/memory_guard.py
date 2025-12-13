#!/usr/bin/env python3
"""
Memory Guard v4.1 - Comprehensive Code Quality Gate for Claude Code

Two-mode operation for optimal speed vs. thoroughness:
- FAST MODE (default): Tier 0-2 only (<300ms) - for PreToolUse during editing
- FULL MODE (--full): All tiers including Tier 3 - for pre-commit validation

Tiers:
- Tier 0: Trivial operation skip (<5ms)
- Tier 1: Pattern-based checks via bash guard (~30ms)
- Tier 2: Fast duplicate detection (<150ms)
- Tier 3: Full Claude CLI + MCP analysis (5-30s) - only in full mode

Claude Code Hook Response Schema:
{
  "continue": "boolean (optional)",
  "suppressOutput": "boolean (optional)",
  "stopReason": "string (optional)",
  "decision": "\"approve\" | \"block\" (optional)",
  "reason": "string (optional)"
}
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from utils.code_analyzer import CodeAnalyzer
except ImportError:
    # Fallback for when run directly
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.code_analyzer import CodeAnalyzer

# Configuration
DEBUG_ENABLED = os.getenv("MEMORY_GUARD_DEBUG", "true").lower() == "true"
TIER2_ENABLED = os.getenv("MEMORY_GUARD_TIER2", "true").lower() == "true"
TIER3_ENABLED = os.getenv("MEMORY_GUARD_TIER3", "true").lower() == "true"

# Mode configuration
# FAST mode: Tier 0-2 only (<300ms) - for PreToolUse during editing
# FULL mode: All tiers including Tier 3 - for pre-commit validation
DEFAULT_MODE = os.getenv("MEMORY_GUARD_MODE", "fast")  # "fast" or "full"
MAX_LATENCY_MS = int(os.getenv("MEMORY_GUARD_MAX_LATENCY_MS", "300"))


class BypassManager:
    """Manages Memory Guard bypass state with simple on/off commands."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.state_file = self.project_root / ".claude" / "guard_state.json"
        self.lock = threading.Lock()

        # Ensure .claude directory exists
        self.state_file.parent.mkdir(exist_ok=True)

    def set_global_state(self, disabled: bool) -> str:
        """Enable or disable Memory Guard globally."""
        try:
            with self.lock:
                state = {"global_disabled": disabled}
                self.state_file.write_text(json.dumps(state, indent=2))

                if disabled:
                    return "🔴 Memory Guard disabled globally"
                else:
                    return "🟢 Memory Guard enabled globally"
        except Exception as e:
            return f"❌ Error setting global guard state: {str(e)}"

    def get_global_status(self) -> str:
        """Get current global Memory Guard status."""
        try:
            is_disabled = self.is_global_disabled()
            if is_disabled:
                return "📊 Memory Guard Status: 🔴 DISABLED GLOBALLY (use 'dups on' to enable)"
            else:
                return "📊 Memory Guard Status: 🟢 ENABLED GLOBALLY (use 'dups off' to disable)"
        except Exception:
            return "📊 Memory Guard Status: 🟢 ENABLED (default)"

    def is_global_disabled(self) -> bool:
        """Check if Memory Guard is disabled globally."""
        try:
            if not self.state_file.exists():
                return False

            with self.lock:
                state = json.loads(self.state_file.read_text())
                return state.get("global_disabled", False)
        except Exception:
            return False


class EntityExtractor:
    """Extract entities from code content."""

    def extract_entities_from_operation(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> list[str]:
        """Extract entity names from Write/Edit operations."""
        entities = []

        if tool_name == "Write":
            content = tool_input.get("content", "")
            entities.extend(self._extract_python_entities(content))

        elif tool_name == "Edit":
            new_string = tool_input.get("new_string", "")
            entities.extend(self._extract_python_entities(new_string))

        elif tool_name == "MultiEdit":
            edits = tool_input.get("edits", [])
            for edit in edits:
                new_string = edit.get("new_string", "")
                entities.extend(self._extract_python_entities(new_string))

        return entities

    def _extract_python_entities(self, content: str) -> list[str]:
        """Extract Python function and class names."""
        entities = []

        # Function patterns
        func_pattern = r"^def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\("
        for match in re.finditer(func_pattern, content, re.MULTILINE):
            entities.append(match.group(1))

        # Class patterns
        class_pattern = r"^class\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        for match in re.finditer(class_pattern, content, re.MULTILINE):
            entities.append(match.group(1))

        return entities


class MemoryGuard:
    """Comprehensive code quality gate - checks duplication, logic, flow integrity, and feature preservation.

    Supports two modes:
    - FAST mode (default): Tier 0-2 only, <300ms target - for PreToolUse during editing
    - FULL mode: All tiers including Tier 3 - for pre-commit validation
    """

    def __init__(
        self, hook_data: dict[str, Any] | None = None, mode: str = DEFAULT_MODE
    ):
        """Initialize Memory Guard.

        Args:
            hook_data: Hook data from Claude Code (optional)
            mode: Operating mode - "fast" (Tier 0-2) or "full" (all tiers)
        """
        self.extractor = EntityExtractor()
        self.code_analyzer = CodeAnalyzer()
        self.mode = mode.lower() if mode else DEFAULT_MODE

        # Early project detection using hook data or current directory
        self.project_root = None
        self.project_name = "unknown"
        self.mcp_collection = "mcp__project-memory__"
        self.bypass_manager = None
        self.current_debug_log = (
            None  # Selected once per hook execution for proper rotation
        )
        self.tier2_detector = None  # Lazy-loaded Tier 2 fast duplicate detector
        self._guard_cache = None  # Lazy-loaded cache

        # Attempt early project detection
        self._early_project_detection(hook_data)

        # Ensure all three debug log files exist (only if debug is enabled)
        if DEBUG_ENABLED:
            self._ensure_debug_files_exist()

    def _early_project_detection(self, hook_data: dict[str, Any] | None = None) -> None:
        """Attempt early project detection from hook data or current directory."""
        try:
            file_path = None

            # Try to get file path from hook data
            if hook_data:
                tool_input = hook_data.get("tool_input", {})
                file_path = tool_input.get("file_path", "")

                # Also try working directory from hook data
                if not file_path:
                    file_path = hook_data.get("cwd", "")

            # Detect project root
            detected_root = self._detect_project_root(file_path if file_path else None)

            if detected_root:
                self.project_root = detected_root
                self.project_name = detected_root.name
                self.mcp_collection = self._detect_mcp_collection()

                # Initialize bypass manager early
                self.bypass_manager = BypassManager(self.project_root)
            else:
                # Fallback: try to detect from current working directory
                self.project_root = self._detect_project_root()
                if self.project_root:
                    self.project_name = self.project_root.name
                    self.mcp_collection = self._detect_mcp_collection()
                    self.bypass_manager = BypassManager(self.project_root)

        except Exception:
            # If detection fails, we'll retry later in process_hook
            pass

    def _detect_project_root(self, file_path: str | None = None) -> Path | None:
        """Detect the project root directory using Claude-first weighted scoring."""
        try:
            marker_weights = {
                "CLAUDE.md": 100,  # Strongest: Claude project marker
                ".claude": 90,  # Second: Claude config directory
                ".git": 80,  # Third: Git repository
                "pyproject.toml": 70,  # Python project
                "package.json": 60,  # Node.js project
                "setup.py": 50,  # Legacy Python
                "Cargo.toml": 40,  # Rust project
                "go.mod": 30,  # Go project
            }

            # Start from target file's directory if provided, otherwise current working directory
            current = Path(file_path).resolve().parent if file_path else Path.cwd()

            best_score = 0
            best_path = None

            # Traverse upward, score each directory
            while current != current.parent:
                score = sum(
                    weight
                    for marker, weight in marker_weights.items()
                    if (current / marker).exists()
                )

                if score > best_score:
                    best_score = score
                    best_path = current

                current = current.parent

            return best_path or Path.cwd()

        except Exception:
            return None

    def _detect_mcp_collection(self) -> str:
        """Detect the MCP collection name for this project."""
        if self.project_root:
            # Check for CLAUDE.md file with MCP instructions
            claude_md = self.project_root / "CLAUDE.md"
            if claude_md.exists():
                try:
                    content = claude_md.read_text()
                    # Look for MCP collection pattern (captures collection names with underscores and hyphens)
                    match = re.search(r"mcp__(.+?)-memory__", content)
                    if match:
                        return f"mcp__{match.group(1)}-memory__"
                except Exception:
                    pass

            # Default to project name based collection
            safe_name = re.sub(r"[^a-zA-Z0-9-]", "-", self.project_name.lower())
            return f"mcp__{safe_name}-memory__"

        return "mcp__project-memory__"

    def save_debug_info(
        self, content: str, mode: str = "a", timestamp: bool = False
    ) -> None:
        """Save debug information to last updated log file (keeps 3 files)."""
        # EMERGENCY DEBUG - always write to tmp regardless of DEBUG_ENABLED
        # try:
        #     with open("/tmp/memory_guard_debug.log", "a") as f:
        #         f.write(f"SAVE_DEBUG_INFO CALLED: mode={mode}, content_len={len(content)}, project_root={self.project_root}\n")
        # except:
        #     pass

        if not DEBUG_ENABLED:
            return
        try:
            if timestamp:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                content = f"[{ts}] {content}"

            # Select log file once per hook execution for proper rotation
            base_dir = self.project_root if self.project_root else Path.cwd()
            if self.current_debug_log is None:
                # First call in this hook execution - select oldest file for rotation
                self.current_debug_log = self._get_current_debug_log(base_dir, True)
            current_log = self.current_debug_log

            with open(current_log, mode) as f:
                f.write(content)
        except Exception as e:
            # Write error to fallback file we can check
            try:
                # Try project logs first, then /tmp
                error_log = base_dir / "logs" / "memory_guard_error.log"
                error_log.parent.mkdir(exist_ok=True)
                with open(error_log, "a") as f:
                    f.write(f"ERROR: {e}\nPATH: {current_log}\nROOT: {base_dir}\n\n")
            except Exception:
                try:
                    with open("/tmp/memory_guard_error.log", "a") as f:
                        f.write(
                            f"ERROR: {e}\nPATH: {current_log}\nROOT: {base_dir}\n\n"
                        )
                except Exception:
                    pass

    def _get_current_debug_log(self, base_dir: Path, is_new_run: bool) -> Path:
        """Get the current debug log file to use."""
        try:
            log_files = [
                base_dir / "logs" / "memory_guard_1.log",
                base_dir / "logs" / "memory_guard_2.log",
                base_dir / "logs" / "memory_guard_3.log",
            ]

            if is_new_run:
                # For new runs, find least recently updated file
                existing_files = [f for f in log_files if f.exists()]
                if not existing_files:
                    return log_files[0]  # Use first file if none exist

                # Find oldest file by modification time
                oldest = min(existing_files, key=lambda f: f.stat().st_mtime)
                return oldest
            else:
                # For same run, find most recently updated file
                existing_files = [f for f in log_files if f.exists()]
                if not existing_files:
                    return log_files[0]  # Use first file if none exist

                # Find newest file by modification time
                newest = max(existing_files, key=lambda f: f.stat().st_mtime)
                return newest

        except Exception:
            return base_dir / "logs" / "memory_guard_1.log"  # Fallback

    def _ensure_debug_files_exist(self) -> None:
        """Create all three debug log files if they don't exist."""
        try:
            base_dir = self.project_root if self.project_root else Path.cwd()
            log_files = [
                base_dir / "logs" / "memory_guard_1.log",
                base_dir / "logs" / "memory_guard_2.log",
                base_dir / "logs" / "memory_guard_3.log",
            ]

            # Ensure logs directory exists
            logs_dir = base_dir / "logs"
            logs_dir.mkdir(exist_ok=True)

            for log_file in log_files:
                if not log_file.exists():
                    # Create the file with a header
                    log_file.touch()
                    with open(log_file, "w") as f:
                        f.write(f"# Memory Guard Log - {log_file.name}\n")
                        f.write(
                            f"# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        )
                        f.write("# This file logs Memory Guard analysis results\n\n")
        except Exception:
            # Silently fail if we can't create files (permissions issue, etc.)
            pass

    def should_process(self, hook_data: dict[str, Any]) -> tuple[bool, str | None]:
        """Determine if this hook event should be processed."""
        # Check global bypass state first
        if self.bypass_manager.is_global_disabled():
            return (
                False,
                "🔴 Memory Guard bypass active globally (use 'dups on' to re-enable)",
            )

        tool_name = hook_data.get("tool_name", "")
        hook_event = hook_data.get("hook_event_name", "")
        tool_input = hook_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")

        # Check event type and tool
        if hook_event != "PreToolUse" or tool_name not in [
            "Write",
            "Edit",
            "MultiEdit",
        ]:
            return False, "Not a relevant operation"

        # Skip documentation and config files
        if file_path:
            file_ext = Path(file_path).suffix.lower()
            skip_extensions = {
                ".md",
                ".txt",
                ".json",
                ".yml",
                ".yaml",
                ".rst",
                ".xml",
            }
            if file_ext in skip_extensions:
                return (
                    False,
                    f"Skipping {file_ext} file - no duplicate checking for documentation/config",
                )

        # Check if within project directory
        if not file_path or not self.project_root:
            return False, f"Outside {self.project_name} project - no duplicate checking"

        try:
            # Check if file is within project root
            file_path_obj = Path(file_path).resolve()
            if not file_path_obj.is_relative_to(self.project_root):
                return (
                    False,
                    f"Outside {self.project_name} project - no duplicate checking",
                )
        except Exception:
            return False, "Invalid file path"

        return True, None

    def check_for_override_comments(self, code_content: str) -> tuple[bool, str]:
        """Check if code contains override comments to allow duplicates."""
        override_patterns = [
            r"#\s*@allow-duplicate(?:\s*:\s*(.+))?",  # Python: # @allow-duplicate: reason
            r"//\s*@allow-duplicate(?:\s*:\s*(.+))?",  # JS/TS/Java: // @allow-duplicate: reason
            r"/\*\s*@allow-duplicate(?:\s*:\s*(.+))?\s*\*/",  # Block: /* @allow-duplicate: reason */
            r"#\s*MEMORY_GUARD_ALLOW(?:\s*:\s*(.+))?",  # Alternative: # MEMORY_GUARD_ALLOW: reason
            r"//\s*MEMORY_GUARD_ALLOW(?:\s*:\s*(.+))?",  # Alternative: // MEMORY_GUARD_ALLOW: reason
        ]

        for pattern in override_patterns:
            match = re.search(pattern, code_content, re.IGNORECASE | re.MULTILINE)
            if match:
                reason = (
                    match.group(1) if match.group(1) else "Override comment detected"
                )
                return True, reason.strip()

        return False, ""

    def is_trivial_operation(self, code_info: str) -> tuple[bool, str]:
        """Check if operation is trivial and should skip guard analysis."""
        analysis = self.code_analyzer.analyze_code(code_info)
        return analysis["is_trivial"], analysis["reason"]

    def has_new_definitions(self, code_info: str) -> bool:
        """Check if code contains NEW function or class definitions."""
        analysis = self.code_analyzer.analyze_code(code_info)
        return analysis["has_definitions"]

    def _get_qdrant_collection_name(self) -> str | None:
        """Extract Qdrant collection name from MCP collection prefix.

        The MCP collection is formatted as 'mcp__collection-name-memory__'.
        We extract 'collection-name-memory' for direct Qdrant access.
        """
        if self.mcp_collection and self.mcp_collection.startswith("mcp__"):
            stripped = self.mcp_collection[5:]  # Remove 'mcp__' prefix
            if stripped.endswith("__"):
                stripped = stripped[:-2]  # Remove '__' suffix
            return stripped
        return None

    def _run_tier2_check(
        self, tool_name: str, tool_input: dict[str, Any], code_info: str
    ) -> dict[str, Any] | None:
        """Run Tier 2 fast duplicate detection. Returns result or None to escalate.

        Tier 2 uses direct Qdrant search to bypass Claude CLI for clear-cut cases:
        - Stage 1: Signature hash (O(1), <5ms) - Exact matches
        - Stage 2: BM25 keyword (<30ms) - High keyword similarity (currently skipped)
        - Stage 3: Semantic search (<100ms) - Vector similarity

        Uses FastDuplicateDetectorRegistry for per-collection detectors to support
        multiple indexed repositories without connection thrashing.

        Returns:
            Result dict with 'decision' and 'reason' if definitive, None to escalate
        """
        if not TIER2_ENABLED:
            return None

        try:
            from utils.fast_duplicate_detector import FastDuplicateDetectorRegistry

            # Extract entities from the operation
            entities = self.extractor.extract_entities_from_operation(
                tool_name, tool_input
            )
            if not entities:
                return None  # No entities to check - escalate to Tier 3

            # Get collection name for Qdrant
            collection = self._get_qdrant_collection_name()
            if not collection:
                return None  # Can't determine collection - escalate

            # Get per-collection detector from registry
            detector = FastDuplicateDetectorRegistry.get_detector(
                collection, self.project_root
            )

            file_path = tool_input.get("file_path", "")
            result = detector.check_duplicate(
                code_info=code_info,
                entity_names=entities,
                file_path=file_path,
                collection=collection,
                project_root=self.project_root,
            )

            # Log Tier 2 result
            self.save_debug_info(
                f"\nTIER 2 ({result.stage}): {result.decision} "
                f"(confidence: {result.confidence:.2f}, latency: {result.latency_ms:.0f}ms)\n"
                f"Reason: {result.reason}\n"
            )

            if result.decision == "escalate":
                return None  # Fall through to Tier 3 (Claude CLI)

            if result.decision == "block":
                return {
                    "decision": "block",
                    "reason": f"🔄 DUPLICATE DETECTED (Tier 2, {result.latency_ms:.0f}ms): {result.reason}",
                    "suppressOutput": False,
                }

            # Approved by Tier 2
            return {
                "reason": f"✅ Tier 2 APPROVED ({result.latency_ms:.0f}ms): {result.reason}",
                "suppressOutput": False,
            }

        except Exception as e:
            self.save_debug_info(f"TIER 2 ERROR: {e}\n")
            return None  # Graceful degradation to Tier 3

    def get_code_info(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Extract code information from the operation."""
        if tool_name == "Write":
            content = tool_input.get("content", "")
            lines = content.split("\n")
            return f"NEW FILE CONTENT ({len(lines)} lines):\n```\n{content}\n```"

        elif tool_name == "Edit":
            old_string = tool_input.get("old_string", "")
            new_string = tool_input.get("new_string", "")
            old_lines = len(old_string.split("\n"))
            new_lines = len(new_string.split("\n"))

            # Add line number context for better AI analysis
            line_info = ""
            add_line_info = ""
            file_path = tool_input.get("file_path", "")
            if file_path and Path(file_path).exists():
                try:
                    with open(file_path) as f:
                        content = f.read()
                    if old_string in content:
                        lines_before = content[: content.find(old_string)].count("\n")
                        line_info = f", line {lines_before + 1}"
                        add_line_info = f", starting line {lines_before + 1}"
                except Exception:
                    pass

            return f"EDIT OPERATION:\nREMOVING ({old_lines} lines{line_info}):\n```\n{old_string}\n```\nADDING ({new_lines} lines{add_line_info}):\n```\n{new_string}\n```"

        elif tool_name == "MultiEdit":
            edits = tool_input.get("edits", [])
            edit_details = []
            for i, edit in enumerate(edits):
                old_string = edit.get("old_string", "")
                new_string = edit.get("new_string", "")
                old_lines = len(old_string.split("\n"))
                new_lines = len(new_string.split("\n"))
                edit_details.append(
                    f"EDIT {i + 1}:\nREMOVING ({old_lines} lines):\n```\n{old_string}\n```\nADDING ({new_lines} lines):\n```\n{new_string}\n```"
                )
            return "MULTIEDIT OPERATION:\n" + "\n\n".join(edit_details)

        return ""

    def build_memory_search_prompt(
        self, file_path: str, tool_name: str, code_info: str
    ) -> str:
        """Build the prompt for comprehensive code quality analysis."""

        return f"""You are a comprehensive code quality gate with access to MCP memory tools.

🚨 ERROR REPORTING: If you cannot access MCP memory tools ({self.mcp_collection}*), report in detail:
- Which exact MCP tool you tried to call (e.g., "{self.mcp_collection}search_similar")
- What parameters you used (query, entityTypes, limit)
- What error message you received (timeout, not found, access denied, etc.)
- Include this in your debug field with prefix "MCP_ERROR:"

OPERATION CONTEXT:
- Project: {self.project_name}
- File: {file_path}
- Operation: {tool_name}
- Code changes:
{code_info}

🔍 COMPREHENSIVE QUALITY ANALYSIS - CHECK ALL 8 DIMENSIONS:

❌ BLOCK FOR ANY OF THESE ISSUES:

🔄 1. CODE DUPLICATION:
- NEW function/class definitions that duplicate existing functionality
- Copy-paste code with minor variations
- Redundant implementations of existing utility functions
- Similar validation/processing patterns already in codebase

🧠 2. LOGIC COMPLETENESS:
- Missing critical error handling for expected failures
- Incomplete input validation (missing edge cases, type checks)
- Missing null/undefined/empty checks where needed
- Incomplete transaction handling (missing rollback, cleanup)
- Missing security validations (auth, permissions, sanitization)

🔗 3. FLOW INTEGRITY:
- Breaking existing API contracts or interfaces
- Removing required parameters without backward compatibility
- Changing function signatures that other code depends on
- Disrupting established data flow patterns
- Breaking existing error handling chains

⚙️ 4. FEATURE PRESERVATION:
- Disabling or removing existing functionality without replacement
- Breaking existing workflows or user journeys
- Removing configuration options that others depend on
- Breaking existing integrations or dependencies
- Removing accessibility features or degrading UX

📊 5. DEPENDENCY IMPACT (NEW):
- Use {self.mcp_collection}read_graph(entity="<entity>", mode="relationships")
  to find what depends on entities being modified
- Report number of files/functions that would be affected
- WARN if changing public API signatures with >3 dependents
- BLOCK if removing exports used by other files

💡 6. SIMILAR CODE SUGGESTIONS (NEW):
- When writing NEW functions, search for existing implementations
- Use {self.mcp_collection}search_similar("<function_name>", entityTypes=["function", "class"])
- If score > 0.7: SUGGEST "Consider using existing <match_name> in <file_path>"
- Help avoid wheel reinvention

🧪 7. TEST COVERAGE (NEW):
- Use {self.mcp_collection}search_similar("<entity_name> test", entityTypes=["function"])
- Check if tests exist for the code being modified
- WARN if modifying untested critical code (auth, payment, data)
- SUGGEST adding tests for new functionality

⚠️ 8. CODE QUALITY MARKERS (NEW):
- Check for FIXME markers (known bugs requiring fix)
- Check for HACK markers (fragile workarounds)
- Check for DEPRECATED markers (needs migration)
- Check for debug statements (print, console.log, breakpoint)
- WARN if any of these are present in new code

✅ ALWAYS ALLOW:
- Function calls, imports, variable assignments, using existing code
- Proper refactoring that maintains functionality
- Adding new features without breaking existing ones
- Improvements that enhance without removing capabilities

⛔ CRITICAL: MANUAL ENTRIES ARE TOXIC TO ANALYSIS
- Manual entries contain OUTDATED ASSUMPTIONS about features that may not exist
- They reference "fixes" and "optimizations" that could be FALSE
- ONLY trust actual code implementations, NEVER trust human descriptions
- If search returns commit references, feature descriptions, or fix notes → CONTAMINATED, ignore

🔍 ANALYSIS PROTOCOL:
1. EXTRACT function/class names from new code being written
2. SEARCH memory for exact duplicates of same functionality using {self.mcp_collection}search_similar
3. SEARCH for related patterns, similar implementations, and existing functionality that could be reused
4. IF similar functions exist: SUGGEST using existing code instead of creating duplicates
5. Use MCP service: {self.mcp_collection}search_similar for related functionality analysis
6. Analyze completeness: missing error cases, validations, edge cases
7. Check integration: dependencies, API contracts, data flows
8. Verify flow integrity: function usage, dependency impact, breaking changes
9. Verify preservation: ensure existing features remain functional
10. EXCLUDE ALL MANUAL ENTRIES AND DOCUMENTATION:
   - IGNORE: documentation files (.md, .txt, .markdown, .rst)
   - IGNORE: manual entries (debugging_pattern, implementation_pattern, integration_pattern, configuration_pattern, architecture_pattern, performance_pattern, knowledge_insight, active_issue, ideas)
   - IGNORE: any human-created analysis, notes, or patterns
   - IGNORE: test/debug files (tests/, debug/, *test*, *debug*) - not production code
   - FOCUS ONLY ON: actual production code implementations (functions, classes, interfaces)

🎯 ANALYSIS STRATEGY (8-DIMENSION CHECK):

STEP 1 - Entity Extraction:
- EXTRACT all function/class names from new code being written

STEP 2 - Duplication Check:
- Use {self.mcp_collection}search_similar("<entity_name>", entityTypes=["function", "class"], limit=5)
- If score > 0.8: BLOCK for duplication
- If score > 0.7: WARN and suggest using existing implementation

STEP 3 - Dependency Impact:
- Use {self.mcp_collection}read_graph(entity="<entity>", mode="relationships")
- Count incoming relations (callers/importers)
- If >3 dependents: WARN about impact
- If removing export: BLOCK

STEP 4 - Test Coverage:
- Use {self.mcp_collection}search_similar("<entity_name> test", entityTypes=["function"])
- Check if matching test functions exist
- If modifying critical code without tests: WARN

STEP 5 - Logic & Flow Analysis:
- Use entityTypes=["implementation"] for detailed code analysis
- Use entityTypes=["relation"] for dependency analysis
- Check for missing error handling, validation, security

STEP 6 - Quality Markers:
- Scan new code for FIXME, HACK, DEPRECATED, debug statements
- WARN if any detected in new code

STEP 7 - Similar Code Suggestions:
- Search for related patterns that could be reused
- SUGGEST existing implementations when applicable

STEP 8 - Feature Preservation:
- Verify existing features remain functional
- Check for breaking changes

📋 RESPONSE FORMAT (JSON only):
⚠️ VALIDATION: If your reason mentions past commits, historical context, or specific feature implementations without showing actual code → you used manual entries! Re-analyze with proper filters.

For BLOCKING (quality issues found): {{
  "hasIssues": true,
  "issueType": "duplication|logic|flow|feature|dependency|test_coverage|quality_marker",
  "reason": "Specific issue description with location and impact",
  "suggestion": "Concrete recommendation to fix the issue",
  "dependents_count": "number of files/functions that depend on modified code (if applicable)",
  "similar_code": "file:line of similar existing implementation (if found)",
  "test_coverage": "exists|missing|unknown",
  "quality_markers": ["FIXME", "HACK", "DEPRECATED", "debug"] (if found),
  "debug": "2-3 sentences: What you found + Why it's problematic + What should be done",
  "turns_used": "number of turns for analysis",
  "steps_summary": ["search_similar(...)", "read_graph(...)", ...]
}}

For APPROVING (no quality issues): {{
  "hasIssues": false,
  "decision": "approve",
  "reason": "Your analysis of why this code is acceptable",
  "dependents_count": "number of files/functions that depend on modified code",
  "similar_code": null,
  "test_coverage": "exists|not_applicable",
  "quality_markers": [],
  "debug": "Your detailed analysis findings",
  "turns_used": "number of turns for analysis",
  "steps_summary": ["search_similar(...)", "read_graph(...)", ...]
}}

🚨 CRITICAL: Thoroughly analyze ALL 8 quality dimensions. Only approve if code passes ALL checks.
IMPORTANT: Return ONLY the JSON object, no explanatory text."""

    def call_claude_cli(self, prompt: str) -> tuple[bool, str, dict[str, Any]]:
        """Call Claude CLI for comprehensive code quality analysis."""
        try:
            # Use project root so Claude CLI can find .mcp.json config
            work_dir = self.project_root if self.project_root else Path.cwd()

            # Allow specific MCP memory tools plus read-only analysis tools
            allowed_tools = f"Read,LS,Bash(ls:*),Glob,Grep,WebFetch,WebSearch,{self.mcp_collection}search_similar,{self.mcp_collection}read_graph,{self.mcp_collection}get_implementation,mcp__github__*"

            result = subprocess.run(
                [
                    "claude",
                    "-p",
                    "--output-format",
                    "json",
                    "--max-turns",
                    "30",
                    "--model",
                    "sonnet",
                    "--allowedTools",
                    allowed_tools,
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(work_dir),
            )

            if result.returncode != 0:
                error_msg = f"Claude CLI failed with return code {result.returncode}"
                crash_info = f"\n{'=' * 60}\nCRASH DETECTED - CLAUDE CLI FAILED:\n"
                crash_info += f"Return code: {result.returncode}\n"
                crash_info += f"STDERR: {result.stderr}\n"
                crash_info += f"STDOUT: {result.stdout}\n"
                crash_info += f"Error: {error_msg}\n"
                self.save_debug_info(crash_info)
                return (
                    False,
                    error_msg,
                    {
                        "error": "cli_failed",
                        "returncode": result.returncode,
                        "stderr": result.stderr,
                    },
                )

            # Log debug info IMMEDIATELY after successful CLI execution (before parsing)
            debug_content = f"\n{'=' * 60}\nQUERY SENT TO CLAUDE:\n{prompt}\n\n"
            debug_content += (
                f"RAW STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}\n"
            )
            self.save_debug_info(debug_content)  # Log before parsing to prevent loss

            # Parse response (may throw exception)
            try:
                return self.parse_claude_response(result.stdout)
            except Exception as parse_error:
                # Log parsing failure with details
                parse_crash_info = f"\n{'=' * 60}\nCRASH DETECTED - PARSE FAILURE:\n"
                parse_crash_info += (
                    f"Parse error: {type(parse_error).__name__}: {str(parse_error)}\n"
                )
                parse_crash_info += f"Raw stdout length: {len(result.stdout)} chars\n"
                parse_crash_info += (
                    "RESULT: Graceful degradation - approving operation\n"
                )
                self.save_debug_info(parse_crash_info)
                raise  # Re-raise to be caught by outer exception handler

        except subprocess.TimeoutExpired as e:
            error_msg = f"Claude CLI timeout after {e.timeout}s"
            crash_info = f"\n{'=' * 60}\nCRASH DETECTED - TIMEOUT:\n"
            crash_info += f"Timeout: {e.timeout}s\n"
            crash_info += f"Command: {e.cmd}\n"
            crash_info += f"Error: {error_msg}\n"
            self.save_debug_info(crash_info)
            return False, error_msg, {"error": "timeout", "timeout": e.timeout}
        except Exception as e:
            error_msg = f"Claude CLI error: {str(e)}"
            crash_info = f"\n{'=' * 60}\nCRASH DETECTED - EXCEPTION:\n"
            crash_info += f"Exception type: {type(e).__name__}\n"
            crash_info += f"Exception message: {str(e)}\n"
            crash_info += f"Error: {error_msg}\n"
            import traceback

            crash_info += f"Traceback:\n{traceback.format_exc()}\n"
            self.save_debug_info(crash_info)
            return (
                False,
                error_msg,
                {
                    "error": "exception",
                    "exception_type": type(e).__name__,
                    "message": str(e),
                },
            )

    def parse_claude_response(self, stdout: str) -> tuple[bool, str, dict[str, Any]]:
        """Parse Claude's response to extract duplicate detection result."""
        try:
            stdout = stdout.strip()

            # Handle CLI wrapper format
            if stdout.startswith('{"type":"result"'):
                cli_response = json.loads(stdout)

                # Check for any CLI errors first
                if cli_response.get("subtype") == "error_max_turns":
                    return (
                        True,
                        f"⚠️  MEMORY GUARD ERROR: Claude CLI hit max turns limit ({cli_response.get('num_turns', '?')} turns). Analysis incomplete.",
                        cli_response,
                    )
                elif cli_response.get("is_error"):
                    return (
                        True,
                        f"⚠️  MEMORY GUARD ERROR: Claude CLI error occurred: {cli_response}",
                        cli_response,
                    )

                result_content = cli_response.get("result", "")

                # Extract JSON from markdown if present
                if "```json" in result_content:
                    json_start = result_content.find("```json\n") + 8
                    json_end = result_content.find("\n```", json_start)
                    inner_json = result_content[json_start:json_end]
                else:
                    inner_json = result_content

                response = json.loads(inner_json)
            else:
                # Direct JSON response
                response = json.loads(stdout)

            # Process comprehensive quality analysis response
            has_issues = response.get("hasIssues", False)
            if has_issues:
                issue_type = response.get("issueType", "unknown")
                issue_icons = {
                    "duplication": "🔄",
                    "logic": "🧠",
                    "flow": "🔗",
                    "feature": "⚙️",
                    "dependency": "📊",
                    "test_coverage": "🧪",
                    "quality_marker": "⚠️",
                }
                icon = issue_icons.get(issue_type, "⚠️")
                reason = f"{icon} CODE QUALITY ISSUE DETECTED ({issue_type.upper()}):\n{response.get('reason', '')}"

                # Add dependency impact info if available
                dependents = response.get("dependents_count")
                if dependents and dependents != "0":
                    reason += f"\n\n📊 IMPACT: {dependents} files/functions depend on this code"

                # Add similar code suggestion if available
                similar = response.get("similar_code")
                if similar and similar != "null":
                    reason += f"\n💡 EXISTING CODE: {similar}"

                # Add test coverage info
                test_cov = response.get("test_coverage")
                if test_cov == "missing":
                    reason += "\n🧪 TEST COVERAGE: Missing - consider adding tests"

                # Add quality markers if found
                markers = response.get("quality_markers", [])
                if markers:
                    reason += f"\n⚠️ QUALITY MARKERS: {', '.join(markers)}"

                # Add analysis steps if available
                if response.get("steps_summary"):
                    steps = response.get("steps_summary", [])
                    if steps:
                        reason += "\n\n🔍 ANALYSIS STEPS:\n"
                        for i, step in enumerate(steps, 1):
                            reason += f"   {i}. {step}\n"

                if response.get("suggestion"):
                    reason += f"\n💡 SUGGESTION: {response.get('suggestion')}"
                return True, reason, response
            else:
                # Build approval message with context
                approval_reason = response.get("reason", "Approved")

                # Add helpful context for approvals
                dependents = response.get("dependents_count")
                if dependents and int(dependents) > 0:
                    approval_reason += f" (Note: {dependents} dependents)"

                test_cov = response.get("test_coverage")
                if test_cov == "exists":
                    approval_reason += " ✅ Tests exist"

                return (
                    False,
                    approval_reason,
                    response,
                )

        except json.JSONDecodeError:
            return False, f"Claude CLI non-JSON response: {stdout[:300]}", {}
        except Exception as e:
            return False, f"Error parsing response: {str(e)}", {}

    def process_hook(self, hook_data: dict[str, Any]) -> dict[str, Any]:
        """Process the hook and return the result."""
        # EMERGENCY DEBUG - track all hook calls
        # try:
        #     with open("/tmp/memory_guard_debug.log", "a") as f:
        #         f.write(f"PROCESS_HOOK CALLED: project_root={self.project_root}, tool={hook_data.get('tool_name')}\n")
        # except:
        #     pass

        # Default result
        result = {"suppressOutput": False}

        try:
            # Get file path from tool input to detect correct project
            tool_input = hook_data.get("tool_input", {})
            file_path = tool_input.get("file_path", "")

            # Detect project root and MCP collection based on target file
            if file_path:
                self.project_root = self._detect_project_root(file_path)
                if self.project_root:
                    self.project_name = self.project_root.name
                    self.mcp_collection = self._detect_mcp_collection()

                    # Initialize bypass manager for the detected project
                    if not self.bypass_manager:
                        self.bypass_manager = BypassManager(self.project_root)

                    # Log the project detection (consolidated to prevent duplication)
                    project_info = f"\n🎯 PROJECT DETECTED:\n- Project: {self.project_name}\n- Root: {self.project_root}\n- MCP Collection: {self.mcp_collection}\n"
                    self.save_debug_info(project_info)

            # Check if we should process this hook
            should_process, skip_reason = self.should_process(hook_data)
            if not should_process:
                result["reason"] = skip_reason
                # Log skipped operation
                skip_info = f"\n{'=' * 60}\nOPERATION SKIPPED:\n"
                skip_info += f"- Reason: {skip_reason}\n"
                self.save_debug_info(skip_info)
                return result

            # Extract information
            tool_name = hook_data.get("tool_name", "")

            # Extract entities (not used but required for analysis flow)
            _ = self.extractor.extract_entities_from_operation(tool_name, tool_input)

            # Get code information
            code_info = self.get_code_info(tool_name, tool_input)
            if not code_info:
                result["reason"] = "No code content to check"
                return result

            # Check override comments before Claude CLI
            has_override, override_reason = self.check_for_override_comments(code_info)
            if has_override:
                result["reason"] = f"Duplicate allowed: {override_reason}"
                self.save_debug_info(f"\nOVERRIDE: {override_reason}\n")
                return result

            # Quick trivial operation check (Tier 1)
            is_trivial, trivial_reason = self.is_trivial_operation(code_info)
            if is_trivial:
                result["reason"] = f"🟢 {trivial_reason}"
                self.save_debug_info(
                    f"\nTIER 1 TRIVIAL OPERATION SKIPPED: {trivial_reason}\n"
                )
                return result

            # Tier 2: Fast duplicate detection (bypasses Claude CLI for clear-cut cases)
            tier2_result = self._run_tier2_check(tool_name, tool_input, code_info)
            if tier2_result is not None:
                return tier2_result

            # In FAST mode, stop here - Tier 3 only runs in FULL mode (pre-commit)
            if self.mode == "fast":
                result["reason"] = (
                    "✅ FAST MODE: Passed Tier 0-2 checks (Tier 3 deferred to pre-commit)"
                )
                self.save_debug_info(
                    "\nFAST MODE: Skipping Tier 3 - deferred to pre-commit validation\n"
                )
                return result

            # Tier 3: Full Claude CLI analysis (only in FULL mode)
            if not TIER3_ENABLED:
                result["reason"] = "✅ Tier 3 disabled - passed Tier 0-2 checks"
                return result

            file_path = tool_input.get("file_path", "unknown")
            prompt = self.build_memory_search_prompt(file_path, tool_name, code_info)

            # Call Claude CLI (Tier 3)
            should_block, reason, claude_response = self.call_claude_cli(prompt)

            # Set result
            result["reason"] = reason
            if should_block:
                result["decision"] = "block"

            # Log final decision
            decision_info = f"\n{'=' * 60}\nFINAL DECISION:\n"
            decision_info += f"- Should Block: {should_block}\n"
            decision_info += f"- Decision: {result.get('decision', 'approve')}\n"
            decision_info += f"- Reason: {reason}\n"
            decision_info += (
                f"- Claude Response:\n{json.dumps(claude_response, indent=2)}\n"
            )
            self.save_debug_info(decision_info)

        except Exception as e:
            # Graceful degradation - always approve on errors
            result["reason"] = f"Error in memory guard: {str(e)}"

            # Log comprehensive crash info
            import traceback

            crash_info = f"\n{'=' * 60}\nCRASH DETECTED - PROCESS_HOOK FAILURE:\n"
            crash_info += f"Exception type: {type(e).__name__}\n"
            crash_info += f"Exception message: {str(e)}\n"
            crash_info += f"Project: {self.project_name}\n"
            crash_info += f"Tool: {hook_data.get('tool_name', 'unknown')}\n"
            crash_info += (
                f"File: {hook_data.get('tool_input', {}).get('file_path', 'unknown')}\n"
            )
            crash_info += f"Traceback:\n{traceback.format_exc()}\n"
            crash_info += f"Hook data: {json.dumps(hook_data, indent=2)}\n"
            crash_info += "RESULT: Graceful degradation - approving operation\n"
            self.save_debug_info(crash_info)

        return result


def main():
    """Main entry point for the hook.

    Supports two invocation modes:
    1. Hook mode (stdin JSON): Called by Claude Code PreToolUse hook
    2. CLI mode (--full/--fast): Called by pre-commit hook or manually

    Examples:
        # Hook mode (default, fast)
        echo '{"tool_name": "Write", ...}' | python memory_guard.py

        # CLI mode for pre-commit (full analysis)
        python memory_guard.py --full --file path/to/file.py --content "..."

        # Analyze specific files
        python memory_guard.py --full --files file1.py file2.py
    """
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Memory Guard - Code Quality Gate for Claude Code"
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Fast mode: Tier 0-2 only (<300ms) - default for PreToolUse",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full mode: All tiers including Tier 3 - for pre-commit validation",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Single file to analyze (for pre-commit mode)",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        type=str,
        help="Multiple files to analyze (for pre-commit mode)",
    )
    parser.add_argument(
        "--content",
        type=str,
        help="Code content to analyze (optional, reads from file if not provided)",
    )

    args = parser.parse_args()

    # Determine mode
    mode = "full" if args.full else "fast"

    # Check if we're in CLI mode (files specified) or hook mode (stdin)
    if args.file or args.files:
        # CLI mode - analyze specified files
        run_cli_mode(args, mode)
    else:
        # Hook mode - read from stdin
        run_hook_mode(mode)


def run_hook_mode(mode: str) -> None:
    """Run in hook mode - read JSON from stdin."""
    try:
        # Read hook data from stdin
        hook_data = json.loads(sys.stdin.read())

        # Initialize guard with hook data for early project detection
        guard = MemoryGuard(hook_data, mode=mode)

        # Clear debug file at start and save initial info with timestamp
        debug_info = (
            f"HOOK CALLED (mode={mode}):\n{json.dumps(hook_data, indent=2)}\n\n"
        )
        debug_info += "PROJECT INFO:\n"
        debug_info += f"- Root: {guard.project_root}\n"
        debug_info += f"- Name: {guard.project_name}\n"
        debug_info += f"- MCP Collection: {guard.mcp_collection}\n"
        debug_info += f"- Mode: {mode.upper()}\n\n"
        guard.save_debug_info(
            debug_info, mode="w", timestamp=True
        )  # Clear file with timestamp

        # Process hook
        result = guard.process_hook(hook_data)

        # Output result
        print(json.dumps(result))

    except Exception as e:
        # Fallback error handling
        result = {
            "reason": f"Fatal error in memory guard: {str(e)}",
            "suppressOutput": False,
        }
        print(json.dumps(result))


def run_cli_mode(args: argparse.Namespace, mode: str) -> None:
    """Run in CLI mode - analyze specified files.

    Used by pre-commit hook for full Tier 3 analysis.
    """
    files_to_analyze = []

    if args.file:
        files_to_analyze.append(args.file)
    if args.files:
        files_to_analyze.extend(args.files)

    if not files_to_analyze:
        print(json.dumps({"error": "No files specified"}))
        sys.exit(1)

    # Initialize guard (no hook data in CLI mode)
    guard = MemoryGuard(mode=mode)

    all_results = []
    any_blocked = False

    for file_path in files_to_analyze:
        file_path = Path(file_path)

        # Skip non-existent files
        if not file_path.exists():
            continue

        # Skip non-code files
        skip_extensions = {".md", ".txt", ".json", ".yml", ".yaml", ".rst", ".xml"}
        if file_path.suffix.lower() in skip_extensions:
            continue

        # Read content
        try:
            if args.content and len(files_to_analyze) == 1:
                content = args.content
            else:
                content = file_path.read_text()
        except Exception as e:
            all_results.append(
                {"file": str(file_path), "error": f"Could not read file: {e}"}
            )
            continue

        # Build hook-like data structure
        hook_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(file_path.resolve()), "content": content},
            "hook_event_name": "PreToolUse",
        }

        # Reinitialize guard with file context
        guard = MemoryGuard(hook_data, mode=mode)

        # Process
        result = guard.process_hook(hook_data)
        result["file"] = str(file_path)

        all_results.append(result)

        if result.get("decision") == "block":
            any_blocked = True

    # Output results
    output = {"mode": mode, "files_analyzed": len(all_results), "results": all_results}

    if any_blocked:
        output["blocked"] = True
        print(json.dumps(output, indent=2))
        sys.exit(1)
    else:
        output["blocked"] = False
        print(json.dumps(output, indent=2))
        sys.exit(0)


if __name__ == "__main__":
    main()
