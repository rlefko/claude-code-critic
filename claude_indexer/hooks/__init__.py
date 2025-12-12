"""
Hooks package for Claude Code integration.

This package provides hook handlers for Claude Code's lifecycle events:
- PostToolUse: Fast quality checks after file writes (<300ms)
- Stop: End-of-turn comprehensive checks (<5s)
- SessionStart: Initialize memory and verify health

The hooks are designed for performance and fail-open behavior.
"""

from .index_queue import IndexQueue
from .post_write import PostWriteExecutor, PostWriteResult, format_findings_for_display
from .stop_check import (
    StopCheckExecutor,
    StopCheckResult,
    format_findings_for_claude,
    format_findings_for_display as format_stop_findings_for_display,
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
]
