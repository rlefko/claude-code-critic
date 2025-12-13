"""Clustering for UI component and style grouping.

This module provides DBSCAN-based clustering for grouping similar
UI components and styles.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from ..models import StaticComponentFingerprint, StyleFingerprint

from .engine import SimilarityEngine


@dataclass
class Cluster:
    """A cluster of similar items."""

    cluster_id: int
    items: list[str] = field(default_factory=list)  # Item IDs
    representative: str | None = None  # Most central item ID
    size: int = 0
    avg_internal_similarity: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "cluster_id": self.cluster_id,
            "items": self.items,
            "representative": self.representative,
            "size": self.size,
            "avg_internal_similarity": self.avg_internal_similarity,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Cluster":
        """Create from dictionary."""
        return cls(
            cluster_id=data["cluster_id"],
            items=data.get("items", []),
            representative=data.get("representative"),
            size=data.get("size", 0),
            avg_internal_similarity=data.get("avg_internal_similarity", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ClusteringResult:
    """Result of clustering operation."""

    clusters: list[Cluster] = field(default_factory=list)
    noise_items: list[str] = field(default_factory=list)  # Items not in any cluster
    total_items: int = 0

    @property
    def cluster_count(self) -> int:
        """Number of clusters found."""
        return len(self.clusters)

    @property
    def clustered_item_count(self) -> int:
        """Number of items in clusters."""
        return sum(c.size for c in self.clusters)

    def get_clusters_by_size(self, min_size: int = 2) -> list[Cluster]:
        """Get clusters with at least min_size items."""
        return [c for c in self.clusters if c.size >= min_size]


class SimilarityClustering:
    """DBSCAN-based clustering for UI components and styles.

    Groups similar items based on multi-signal similarity scores
    from the SimilarityEngine.
    """

    def __init__(
        self,
        similarity_engine: SimilarityEngine,
        min_cluster_size: int = 2,
        eps: float = 0.15,  # 1 - similarity threshold (0.85 similarity)
        min_samples: int = 2,
    ):
        """Initialize the clustering engine.

        Args:
            similarity_engine: SimilarityEngine for computing similarities.
            min_cluster_size: Minimum items to form a cluster.
            eps: DBSCAN epsilon (distance threshold, 1 - similarity).
            min_samples: DBSCAN minimum samples per core point.
        """
        self.similarity_engine = similarity_engine
        self.min_cluster_size = min_cluster_size
        self.eps = eps
        self.min_samples = min_samples

    def cluster_components(
        self,
        components: list["StaticComponentFingerprint"],
        embeddings: list[list[float]] | None = None,
    ) -> ClusteringResult:
        """Cluster components by similarity.

        Args:
            components: List of component fingerprints.
            embeddings: Optional embeddings for components.

        Returns:
            ClusteringResult with clusters and noise.
        """
        if len(components) < 2:
            return ClusteringResult(total_items=len(components))

        # Build similarity matrix
        similarity_matrix = self._build_component_similarity_matrix(
            components, embeddings
        )

        # Convert to distance matrix (1 - similarity)
        distance_matrix = 1.0 - similarity_matrix

        # Run DBSCAN
        labels = self._run_dbscan(distance_matrix)

        # Build clusters from labels
        return self._build_clusters(
            components, labels, similarity_matrix, get_id=self._get_component_id
        )

    def cluster_styles(
        self,
        styles: list["StyleFingerprint"],
    ) -> ClusteringResult:
        """Cluster styles by similarity.

        Args:
            styles: List of style fingerprints.

        Returns:
            ClusteringResult with clusters and noise.
        """
        if len(styles) < 2:
            return ClusteringResult(total_items=len(styles))

        # Build similarity matrix
        similarity_matrix = self._build_style_similarity_matrix(styles)

        # Convert to distance matrix
        distance_matrix = 1.0 - similarity_matrix

        # Run DBSCAN
        labels = self._run_dbscan(distance_matrix)

        # Build clusters from labels
        return self._build_clusters(
            styles, labels, similarity_matrix, get_id=self._get_style_id
        )

    def _build_component_similarity_matrix(
        self,
        components: list["StaticComponentFingerprint"],
        embeddings: list[list[float]] | None = None,
    ) -> np.ndarray:
        """Build pairwise similarity matrix for components.

        Args:
            components: List of component fingerprints.
            embeddings: Optional embeddings.

        Returns:
            NumPy array of pairwise similarities.
        """
        n = len(components)
        matrix = np.zeros((n, n))

        for i in range(n):
            matrix[i, i] = 1.0  # Self-similarity

            for j in range(i + 1, n):
                emb_i = embeddings[i] if embeddings and i < len(embeddings) else None
                emb_j = embeddings[j] if embeddings and j < len(embeddings) else None

                result = self.similarity_engine.compute_component_similarity(
                    components[i], components[j], emb_i, emb_j
                )

                matrix[i, j] = result.combined_score
                matrix[j, i] = result.combined_score

        return matrix

    def _build_style_similarity_matrix(
        self,
        styles: list["StyleFingerprint"],
    ) -> np.ndarray:
        """Build pairwise similarity matrix for styles.

        Args:
            styles: List of style fingerprints.

        Returns:
            NumPy array of pairwise similarities.
        """
        n = len(styles)
        matrix = np.zeros((n, n))

        for i in range(n):
            matrix[i, i] = 1.0

            for j in range(i + 1, n):
                result = self.similarity_engine.compute_style_similarity(
                    styles[i], styles[j]
                )

                matrix[i, j] = result.combined_score
                matrix[j, i] = result.combined_score

        return matrix

    def _run_dbscan(self, distance_matrix: np.ndarray) -> list[int]:
        """Run DBSCAN clustering on distance matrix.

        Args:
            distance_matrix: Precomputed distance matrix.

        Returns:
            List of cluster labels (-1 for noise).
        """
        try:
            from sklearn.cluster import DBSCAN

            clustering = DBSCAN(
                eps=self.eps,
                min_samples=self.min_samples,
                metric="precomputed",
            )

            labels = clustering.fit_predict(distance_matrix)
            return labels.tolist()

        except ImportError:
            # Fallback to simple threshold-based clustering
            return self._simple_clustering(distance_matrix)

    def _simple_clustering(self, distance_matrix: np.ndarray) -> list[int]:
        """Simple fallback clustering when sklearn unavailable.

        Uses threshold-based connected components.

        Args:
            distance_matrix: Precomputed distance matrix.

        Returns:
            List of cluster labels.
        """
        n = distance_matrix.shape[0]
        labels = [-1] * n
        current_cluster = 0

        for i in range(n):
            if labels[i] != -1:
                continue

            # Find all items within eps distance
            neighbors = [
                j for j in range(n) if distance_matrix[i, j] <= self.eps and i != j
            ]

            if len(neighbors) >= self.min_samples - 1:
                # Start new cluster
                labels[i] = current_cluster

                # Add neighbors to cluster
                for neighbor in neighbors:
                    if labels[neighbor] == -1:
                        labels[neighbor] = current_cluster

                current_cluster += 1

        return labels

    def _build_clusters(
        self,
        items: list,
        labels: list[int],
        similarity_matrix: np.ndarray,
        get_id,
    ) -> ClusteringResult:
        """Build Cluster objects from DBSCAN labels.

        Args:
            items: List of items that were clustered.
            labels: Cluster labels from DBSCAN.
            similarity_matrix: Pairwise similarity matrix.
            get_id: Function to get ID from item.

        Returns:
            ClusteringResult with clusters and noise.
        """
        clusters_dict: dict[int, list[int]] = {}
        noise_indices = []

        for idx, label in enumerate(labels):
            if label == -1:
                noise_indices.append(idx)
            else:
                if label not in clusters_dict:
                    clusters_dict[label] = []
                clusters_dict[label].append(idx)

        # Build cluster objects
        clusters = []
        for cluster_id, indices in clusters_dict.items():
            if len(indices) < self.min_cluster_size:
                noise_indices.extend(indices)
                continue

            item_ids = [get_id(items[i]) for i in indices]

            # Compute average internal similarity
            avg_sim = self._compute_avg_similarity(indices, similarity_matrix)

            # Find representative (most similar to others)
            representative_idx = self._find_representative(indices, similarity_matrix)
            representative = get_id(items[representative_idx])

            clusters.append(
                Cluster(
                    cluster_id=cluster_id,
                    items=item_ids,
                    representative=representative,
                    size=len(item_ids),
                    avg_internal_similarity=avg_sim,
                )
            )

        # Sort clusters by size descending
        clusters.sort(key=lambda c: c.size, reverse=True)

        noise_ids = [get_id(items[i]) for i in noise_indices]

        return ClusteringResult(
            clusters=clusters,
            noise_items=noise_ids,
            total_items=len(items),
        )

    def _compute_avg_similarity(
        self,
        indices: list[int],
        similarity_matrix: np.ndarray,
    ) -> float:
        """Compute average pairwise similarity within cluster.

        Args:
            indices: Indices of items in cluster.
            similarity_matrix: Full similarity matrix.

        Returns:
            Average internal similarity.
        """
        if len(indices) < 2:
            return 1.0

        total = 0.0
        count = 0

        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                total += similarity_matrix[indices[i], indices[j]]
                count += 1

        return total / count if count > 0 else 0.0

    def _find_representative(
        self,
        indices: list[int],
        similarity_matrix: np.ndarray,
    ) -> int:
        """Find the most representative item (highest avg similarity to others).

        Args:
            indices: Indices of items in cluster.
            similarity_matrix: Full similarity matrix.

        Returns:
            Index of representative item.
        """
        if len(indices) == 1:
            return indices[0]

        best_idx = indices[0]
        best_avg = 0.0

        for i in indices:
            avg = sum(similarity_matrix[i, j] for j in indices if j != i)
            avg /= len(indices) - 1

            if avg > best_avg:
                best_avg = avg
                best_idx = i

        return best_idx

    def _get_component_id(self, component: "StaticComponentFingerprint") -> str:
        """Get ID for a component."""
        if component.embedding_id:
            return component.embedding_id
        if component.source_ref:
            return f"{component.source_ref.file_path}:{component.source_ref.start_line}"
        return component.structure_hash[:16]

    def _get_style_id(self, style: "StyleFingerprint") -> str:
        """Get ID for a style."""
        if style.source_refs:
            ref = style.source_refs[0]
            return f"{ref.file_path}:{ref.start_line}"
        return style.exact_hash[:16]


__all__ = [
    "Cluster",
    "ClusteringResult",
    "SimilarityClustering",
]
