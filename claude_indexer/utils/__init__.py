"""Utility modules for claude-indexer."""

from .claudeignore_parser import ClaudeIgnoreParser
from .hierarchical_ignore import HierarchicalIgnoreManager
from .lazy import LazyModule, LazyProperty, lazy_init, lazy_property

__all__ = [
    "ClaudeIgnoreParser",
    "HierarchicalIgnoreManager",
    "lazy_property",
    "lazy_init",
    "LazyProperty",
    "LazyModule",
]
