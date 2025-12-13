"""Similarity engine for UI component and style comparison.

This module provides multi-signal similarity scoring combining
semantic, structural, and style-based signals.
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from ..normalizers.hashing import simhash_similarity

if TYPE_CHECKING:
    from ..config import UIQualityConfig
    from ..models import StaticComponentFingerprint, StyleFingerprint


class SimilarityClassification(Enum):
    """Classification of similarity between two items."""

    DUPLICATE = "duplicate"  # >= 0.95 combined score
    NEAR_DUPLICATE = "near_duplicate"  # >= 0.80 combined score
    SIMILAR = "similar"  # >= 0.60 combined score
    DISTINCT = "distinct"  # < 0.60 combined score


@dataclass
class SimilarityResult:
    """Result of similarity comparison between two items."""

    source_id: str
    target_id: str
    semantic_score: float = 0.0  # 0.0-1.0 from embedding similarity
    structural_score: float = 0.0  # 0.0-1.0 from hash comparison
    style_score: float = 0.0  # 0.0-1.0 from style hash comparison
    combined_score: float = 0.0  # Weighted combination
    classification: SimilarityClassification = SimilarityClassification.DISTINCT

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "semantic_score": self.semantic_score,
            "structural_score": self.structural_score,
            "style_score": self.style_score,
            "combined_score": self.combined_score,
            "classification": self.classification.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimilarityResult":
        """Create from dictionary."""
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            semantic_score=data.get("semantic_score", 0.0),
            structural_score=data.get("structural_score", 0.0),
            style_score=data.get("style_score", 0.0),
            combined_score=data.get("combined_score", 0.0),
            classification=SimilarityClassification(
                data.get("classification", "distinct")
            ),
        )


@dataclass
class SimilarityEngineConfig:
    """Configuration for the similarity engine."""

    # Weights for multi-signal scoring
    semantic_weight: float = 0.5
    structural_weight: float = 0.3
    style_weight: float = 0.2

    # Thresholds for classification
    duplicate_threshold: float = 0.95
    near_duplicate_threshold: float = 0.80
    similar_threshold: float = 0.60

    # Search limits
    max_neighbors: int = 10


class SimilarityEngine:
    """Multi-signal similarity scoring for UI components and styles.

    Combines semantic (embedding-based), structural (hash-based),
    and style (style ref-based) signals for accurate similarity
    detection.
    """

    def __init__(
        self,
        config: "UIQualityConfig | None" = None,
        engine_config: SimilarityEngineConfig | None = None,
    ):
        """Initialize the similarity engine.

        Args:
            config: UI quality configuration.
            engine_config: Engine-specific configuration.
        """
        self.config = config
        self.engine_config = engine_config or SimilarityEngineConfig()

        # Use config thresholds if available
        if config:
            thresholds = config.gating.similarity_thresholds
            self.engine_config.duplicate_threshold = thresholds.duplicate
            self.engine_config.near_duplicate_threshold = thresholds.near_duplicate

    def compute_component_similarity(
        self,
        component1: "StaticComponentFingerprint",
        component2: "StaticComponentFingerprint",
        embedding1: list[float] | None = None,
        embedding2: list[float] | None = None,
    ) -> SimilarityResult:
        """Compute similarity between two components.

        Args:
            component1: First component fingerprint.
            component2: Second component fingerprint.
            embedding1: Optional pre-computed embedding for component1.
            embedding2: Optional pre-computed embedding for component2.

        Returns:
            SimilarityResult with all scores.
        """
        # Compute semantic similarity if embeddings provided
        semantic = 0.0
        if embedding1 and embedding2:
            semantic = self._cosine_similarity(embedding1, embedding2)

        # Compute structural similarity from structure hashes
        structural = self._compute_structural_similarity(
            component1.structure_hash,
            component2.structure_hash,
        )

        # Compute style similarity from style refs
        style = self._compute_style_ref_similarity(
            component1.style_refs,
            component2.style_refs,
        )

        # Combine scores
        combined = self._combine_scores(semantic, structural, style)
        classification = self._classify(combined)

        # Generate IDs
        source_id = self._get_component_id(component1)
        target_id = self._get_component_id(component2)

        return SimilarityResult(
            source_id=source_id,
            target_id=target_id,
            semantic_score=semantic,
            structural_score=structural,
            style_score=style,
            combined_score=combined,
            classification=classification,
        )

    def compute_style_similarity(
        self,
        style1: "StyleFingerprint",
        style2: "StyleFingerprint",
    ) -> SimilarityResult:
        """Compute similarity between two style fingerprints.

        Args:
            style1: First style fingerprint.
            style2: Second style fingerprint.

        Returns:
            SimilarityResult with all scores.
        """
        # For styles, we use hash-based similarity primarily
        semantic = 0.0  # Could add embedding support later

        # Structural is based on exact hash match
        structural = 1.0 if style1.exact_hash == style2.exact_hash else 0.0

        # Style similarity from near hash
        style_sim = simhash_similarity(style1.near_hash, style2.near_hash)

        # For styles, weight style similarity more heavily
        combined = structural * 0.4 + style_sim * 0.6
        classification = self._classify(combined)

        # Generate IDs from source refs
        source_id = self._get_style_id(style1)
        target_id = self._get_style_id(style2)

        return SimilarityResult(
            source_id=source_id,
            target_id=target_id,
            semantic_score=semantic,
            structural_score=structural,
            style_score=style_sim,
            combined_score=combined,
            classification=classification,
        )

    def find_similar_components(
        self,
        target: "StaticComponentFingerprint",
        candidates: list["StaticComponentFingerprint"],
        target_embedding: list[float] | None = None,
        candidate_embeddings: list[list[float]] | None = None,
        min_score: float = 0.0,
    ) -> list[SimilarityResult]:
        """Find components similar to the target.

        Args:
            target: Target component to find matches for.
            candidates: List of candidate components.
            target_embedding: Optional embedding for target.
            candidate_embeddings: Optional embeddings for candidates.
            min_score: Minimum combined score to include.

        Returns:
            List of SimilarityResults sorted by combined score.
        """
        results = []

        for i, candidate in enumerate(candidates):
            # Skip self-comparison
            if self._get_component_id(target) == self._get_component_id(candidate):
                continue

            # Get embeddings if available
            c_embedding = None
            if candidate_embeddings and i < len(candidate_embeddings):
                c_embedding = candidate_embeddings[i]

            result = self.compute_component_similarity(
                target, candidate, target_embedding, c_embedding
            )

            if result.combined_score >= min_score:
                results.append(result)

        # Sort by combined score descending
        results.sort(key=lambda r: r.combined_score, reverse=True)

        # Limit to max neighbors
        return results[: self.engine_config.max_neighbors]

    def find_similar_styles(
        self,
        target: "StyleFingerprint",
        candidates: list["StyleFingerprint"],
        min_score: float = 0.0,
    ) -> list[SimilarityResult]:
        """Find styles similar to the target.

        Args:
            target: Target style to find matches for.
            candidates: List of candidate styles.
            min_score: Minimum combined score to include.

        Returns:
            List of SimilarityResults sorted by combined score.
        """
        results = []

        for candidate in candidates:
            # Skip self-comparison
            if target.exact_hash == candidate.exact_hash:
                # Same hash = exact duplicate, include with score 1.0
                result = SimilarityResult(
                    source_id=self._get_style_id(target),
                    target_id=self._get_style_id(candidate),
                    structural_score=1.0,
                    style_score=1.0,
                    combined_score=1.0,
                    classification=SimilarityClassification.DUPLICATE,
                )
                if result.source_id != result.target_id:
                    results.append(result)
                continue

            result = self.compute_style_similarity(target, candidate)

            if result.combined_score >= min_score:
                results.append(result)

        # Sort by combined score descending
        results.sort(key=lambda r: r.combined_score, reverse=True)

        return results[: self.engine_config.max_neighbors]

    def _cosine_similarity(
        self,
        vec1: list[float],
        vec2: list[float],
    ) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec1: First vector.
            vec2: Second vector.

        Returns:
            Cosine similarity between 0.0 and 1.0.
        """
        if not vec1 or not vec2:
            return 0.0

        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return max(0.0, min(1.0, dot_product / (norm1 * norm2)))

    def _compute_structural_similarity(
        self,
        hash1: str,
        hash2: str,
    ) -> float:
        """Compute structural similarity from structure hashes.

        Args:
            hash1: First structure hash.
            hash2: Second structure hash.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        if not hash1 or not hash2:
            return 0.0

        # Exact match
        if hash1 == hash2:
            return 1.0

        # Use SimHash similarity if hashes are hex strings
        return simhash_similarity(hash1, hash2)

    def _compute_style_ref_similarity(
        self,
        refs1: list[str],
        refs2: list[str],
    ) -> float:
        """Compute Jaccard similarity of style references.

        Args:
            refs1: First list of style references.
            refs2: Second list of style references.

        Returns:
            Jaccard similarity between 0.0 and 1.0.
        """
        if not refs1 or not refs2:
            return 0.0

        set1 = set(refs1)
        set2 = set(refs2)

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        return intersection / union

    def _combine_scores(
        self,
        semantic: float,
        structural: float,
        style: float,
    ) -> float:
        """Combine scores with configured weights.

        Args:
            semantic: Semantic similarity score.
            structural: Structural similarity score.
            style: Style similarity score.

        Returns:
            Weighted combined score.
        """
        return (
            semantic * self.engine_config.semantic_weight
            + structural * self.engine_config.structural_weight
            + style * self.engine_config.style_weight
        )

    def _classify(self, combined_score: float) -> SimilarityClassification:
        """Classify based on combined score.

        Args:
            combined_score: Combined similarity score.

        Returns:
            SimilarityClassification enum value.
        """
        if combined_score >= self.engine_config.duplicate_threshold:
            return SimilarityClassification.DUPLICATE
        elif combined_score >= self.engine_config.near_duplicate_threshold:
            return SimilarityClassification.NEAR_DUPLICATE
        elif combined_score >= self.engine_config.similar_threshold:
            return SimilarityClassification.SIMILAR
        else:
            return SimilarityClassification.DISTINCT

    def _get_component_id(self, component: "StaticComponentFingerprint") -> str:
        """Get unique ID for a component.

        Args:
            component: Component fingerprint.

        Returns:
            Unique identifier string.
        """
        if component.embedding_id:
            return component.embedding_id
        if component.source_ref:
            return f"{component.source_ref.file_path}:{component.source_ref.start_line}"
        return component.structure_hash[:16]

    def _get_style_id(self, style: "StyleFingerprint") -> str:
        """Get unique ID for a style.

        Args:
            style: Style fingerprint.

        Returns:
            Unique identifier string.
        """
        if style.source_refs:
            ref = style.source_refs[0]
            return f"{ref.file_path}:{ref.start_line}"
        return style.exact_hash[:16]


__all__ = [
    "SimilarityEngine",
    "SimilarityEngineConfig",
    "SimilarityResult",
    "SimilarityClassification",
]
