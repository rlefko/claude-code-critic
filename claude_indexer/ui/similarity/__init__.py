"""UI similarity engine package.

This package provides multi-signal similarity scoring and
clustering for UI components and styles.
"""

from .clustering import Cluster, ClusteringResult, SimilarityClustering
from .engine import (
    SimilarityClassification,
    SimilarityEngine,
    SimilarityEngineConfig,
    SimilarityResult,
)

__all__ = [
    # Engine
    "SimilarityEngine",
    "SimilarityEngineConfig",
    "SimilarityResult",
    "SimilarityClassification",
    # Clustering
    "Cluster",
    "ClusteringResult",
    "SimilarityClustering",
]
