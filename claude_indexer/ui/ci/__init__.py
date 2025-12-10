"""CI audit module for UI consistency checking.

This package provides tools for CI-tier UI consistency analysis,
including cross-file clustering, baseline management, and caching.

Main components:
- cache: Fingerprint caching for repeated audit runs
- cross_file_analyzer: Cross-file duplicate detection and clustering
- baseline: Baseline management and cleanup map generation
- audit_runner: Main CI audit orchestration
"""

from .audit_runner import CIAuditConfig, CIAuditResult, CIAuditRunner
from .baseline import (
    BaselineEntry,
    BaselineManager,
    BaselineReport,
    CleanupItem,
    CleanupMap,
)
from .cache import CacheEntry, CacheManager, CacheMetadata, FingerprintCache
from .cross_file_analyzer import (
    CrossFileAnalyzer,
    CrossFileClusterResult,
    CrossFileDuplicate,
)

__all__ = [
    # Cache
    "CacheEntry",
    "CacheMetadata",
    "FingerprintCache",
    "CacheManager",
    # Cross-file analysis
    "CrossFileDuplicate",
    "CrossFileClusterResult",
    "CrossFileAnalyzer",
    # Baseline
    "BaselineEntry",
    "BaselineReport",
    "CleanupItem",
    "CleanupMap",
    "BaselineManager",
    # Audit runner
    "CIAuditConfig",
    "CIAuditResult",
    "CIAuditRunner",
]
