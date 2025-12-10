"""Critique engine for evidence-backed UI design analysis.

This module provides the CritiqueEngine and related analyzers for generating
comprehensive, evidence-backed design critiques as part of the /redesign command.
"""

from .affordance import AffordanceAnalyzer
from .consistency import ConsistencyAnalyzer
from .engine import CritiqueEngine, CritiqueItem, CritiqueReport, CritiqueSummary
from .hierarchy import HierarchyAnalyzer

__all__ = [
    "AffordanceAnalyzer",
    "ConsistencyAnalyzer",
    "CritiqueEngine",
    "CritiqueItem",
    "CritiqueReport",
    "CritiqueSummary",
    "HierarchyAnalyzer",
]
