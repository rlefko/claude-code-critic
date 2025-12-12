"""
Hooks package for Claude Code integration.

This package provides hook handlers for Claude Code's lifecycle events:
- PostToolUse: Fast quality checks after file writes (<300ms)
- Stop: End-of-turn comprehensive checks (<5s)
- SessionStart: Initialize memory and verify health

The hooks are designed for performance and fail-open behavior.

Milestone 3.3 adds the self-repair loop:
- RepairSession: Tracks retry attempts per session
- RepairSessionManager: Manages session state persistence
- FixSuggestion: Fix suggestions for findings
- FixSuggestionGenerator: Generates fix suggestions from rules
- RepairCheckResult: Extended result with repair context
- run_stop_check_with_repair: Stop check with retry tracking
"""

from .fix_generator import FixSuggestion, FixSuggestionGenerator
from .index_queue import IndexQueue
from .post_write import PostWriteExecutor, PostWriteResult, format_findings_for_display
from .repair_result import RepairCheckResult
from .repair_session import RepairSession, RepairSessionManager
from .stop_check import (
    StopCheckExecutor,
    StopCheckResult,
    format_findings_for_claude,
    format_findings_for_display as format_stop_findings_for_display,
    run_stop_check_with_repair,
)

__all__ = [
    # PostToolUse hook
    "PostWriteExecutor",
    "PostWriteResult",
    "format_findings_for_display",
    # Stop hook
    "StopCheckExecutor",
    "StopCheckResult",
    "format_findings_for_claude",
    "format_stop_findings_for_display",
    # Indexing queue
    "IndexQueue",
    # Self-repair loop (Milestone 3.3)
    "RepairSession",
    "RepairSessionManager",
    "FixSuggestion",
    "FixSuggestionGenerator",
    "RepairCheckResult",
    "run_stop_check_with_repair",
]
