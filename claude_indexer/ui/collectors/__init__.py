"""Collectors for UI consistency checking.

This module provides collectors that gather UI-related information from
source code, git diff, and runtime analysis for analysis.
"""

from .base import (
    BaseSourceAdapter,
    ExtractedComponent,
    ExtractedStyle,
    ExtractionResult,
)
from .git_diff import (
    DiffResult,
    FileChange,
    GitDiffCollector,
)
from .source import (
    SourceCollector,
)

# Runtime collectors (Playwright-based) - imported conditionally
try:
    from .element_targeting import (
        DiscoveredElement,
        ElementTargetingStrategy,
        UIRole,
    )
    from .pseudo_states import (
        PseudoState,
        PseudoStateCapture,
        PseudoStateStyles,
    )
    from .runtime import (
        CrawlResult,
        CrawlTarget,
        RuntimeCollector,
    )
    from .screenshots import (
        ElementScreenshot,
        ScreenshotCapture,
        VisualCluster,
        VisualClusteringEngine,
        VisualClusteringResult,
    )
    from .style_capture import (
        CapturedStyles,
        ComputedStyleCapture,
    )

    RUNTIME_AVAILABLE = True
except ImportError:
    RUNTIME_AVAILABLE = False

__all__ = [
    # Git diff collection
    "FileChange",
    "DiffResult",
    "GitDiffCollector",
    # Source extraction
    "ExtractedComponent",
    "ExtractedStyle",
    "ExtractionResult",
    "BaseSourceAdapter",
    "SourceCollector",
    # Runtime collection (Phase 6)
    "CrawlTarget",
    "CrawlResult",
    "RuntimeCollector",
    "UIRole",
    "DiscoveredElement",
    "ElementTargetingStrategy",
    "CapturedStyles",
    "ComputedStyleCapture",
    "PseudoState",
    "PseudoStateStyles",
    "PseudoStateCapture",
    "ElementScreenshot",
    "VisualCluster",
    "VisualClusteringResult",
    "ScreenshotCapture",
    "VisualClusteringEngine",
]
