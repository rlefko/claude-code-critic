"""Git integration for change detection and incremental indexing.

This module provides git-aware change detection to enable efficient
incremental indexing by leveraging git's change tracking capabilities.
"""

from .change_detector import ChangeSet, GitChangeDetector

__all__ = ["GitChangeDetector", "ChangeSet"]
