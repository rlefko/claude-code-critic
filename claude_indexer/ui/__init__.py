"""UI consistency checking module for Claude Code Memory.

This package provides tools for detecting and preventing UI entropy
through design token validation, duplicate detection, and consistency
analysis.

Main components:
- models: Core data models (SymbolRef, StyleFingerprint, Finding, etc.)
- tokens: Design token models (ColorToken, SpacingToken, TokenSet, etc.)
- config: Configuration loading and validation
- storage: Qdrant collection management for UI data
- token_adapters: Adapters for extracting tokens from CSS, Tailwind, JSON
"""

from .config import (
    UIConfigLoader,
    UIQualityConfig,
    load_ui_config,
)
from .models import (
    Evidence,
    EvidenceType,
    Finding,
    LayoutBox,
    RuntimeElementFingerprint,
    Severity,
    StaticComponentFingerprint,
    StyleFingerprint,
    SymbolKind,
    SymbolRef,
    UIAnalysisResult,
    Visibility,
)
from .storage import (
    UI_RUNTIME_COLLECTION,
    UI_STYLES_COLLECTION,
    UI_SYMBOLS_COLLECTION,
    UICollectionManager,
    create_component_payload,
    create_runtime_payload,
    create_style_payload,
    generate_ui_point_id,
)
from .tokens import (
    ColorToken,
    RadiusToken,
    ShadowToken,
    SpacingToken,
    TokenSet,
    TypographyToken,
)

__all__ = [
    # Models
    "Severity",
    "SymbolKind",
    "EvidenceType",
    "Visibility",
    "SymbolRef",
    "Evidence",
    "StyleFingerprint",
    "StaticComponentFingerprint",
    "LayoutBox",
    "RuntimeElementFingerprint",
    "Finding",
    "UIAnalysisResult",
    # Tokens
    "ColorToken",
    "SpacingToken",
    "RadiusToken",
    "TypographyToken",
    "ShadowToken",
    "TokenSet",
    # Config
    "UIQualityConfig",
    "UIConfigLoader",
    "load_ui_config",
    # Storage
    "UICollectionManager",
    "UI_SYMBOLS_COLLECTION",
    "UI_STYLES_COLLECTION",
    "UI_RUNTIME_COLLECTION",
    "create_component_payload",
    "create_style_payload",
    "create_runtime_payload",
    "generate_ui_point_id",
]
