"""Cross-file analysis for UI consistency checking.

This module provides cross-file duplicate detection and clustering
for style and component fingerprints.
"""

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import UIQualityConfig
    from ..models import StaticComponentFingerprint, StyleFingerprint

from ..similarity.clustering import Cluster, ClusteringResult, SimilarityClustering
from ..similarity.engine import SimilarityEngine


@dataclass
class CrossFileDuplicate:
    """A duplicate found across multiple files.

    Represents a style or component that appears in multiple files
    with high similarity, indicating a potential consolidation opportunity.
    """

    duplicate_type: str  # "style" or "component"
    cluster_id: int
    file_locations: list[str] = field(default_factory=list)  # file:line refs
    similarity_score: float = 0.0
    recommended_action: str = "review"  # "extract", "consolidate", "remove"
    impact_estimate: str = "medium"  # "high", "medium", "low"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "duplicate_type": self.duplicate_type,
            "cluster_id": self.cluster_id,
            "file_locations": self.file_locations,
            "similarity_score": self.similarity_score,
            "recommended_action": self.recommended_action,
            "impact_estimate": self.impact_estimate,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrossFileDuplicate":
        """Create from dictionary."""
        return cls(
            duplicate_type=data["duplicate_type"],
            cluster_id=data["cluster_id"],
            file_locations=data.get("file_locations", []),
            similarity_score=data.get("similarity_score", 0.0),
            recommended_action=data.get("recommended_action", "review"),
            impact_estimate=data.get("impact_estimate", "medium"),
            details=data.get("details", {}),
        )


@dataclass
class CrossFileClusterResult:
    """Result of cross-file clustering analysis.

    Contains clustering results for both styles and components,
    along with identified cross-file duplicates.
    """

    style_clusters: ClusteringResult = field(default_factory=ClusteringResult)
    component_clusters: ClusteringResult = field(default_factory=ClusteringResult)
    cross_file_duplicates: list[CrossFileDuplicate] = field(default_factory=list)
    analysis_time_ms: float = 0.0
    total_styles_analyzed: int = 0
    total_components_analyzed: int = 0

    @property
    def duplicate_count(self) -> int:
        """Total number of cross-file duplicates found."""
        return len(self.cross_file_duplicates)

    @property
    def style_cluster_count(self) -> int:
        """Number of style clusters found."""
        return self.style_clusters.cluster_count

    @property
    def component_cluster_count(self) -> int:
        """Number of component clusters found."""
        return self.component_clusters.cluster_count

    def get_high_impact_duplicates(self) -> list[CrossFileDuplicate]:
        """Get duplicates with high impact estimate."""
        return [d for d in self.cross_file_duplicates if d.impact_estimate == "high"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "style_clusters": {
                "cluster_count": self.style_clusters.cluster_count,
                "total_items": self.style_clusters.total_items,
                "clusters": [c.to_dict() for c in self.style_clusters.clusters],
            },
            "component_clusters": {
                "cluster_count": self.component_clusters.cluster_count,
                "total_items": self.component_clusters.total_items,
                "clusters": [c.to_dict() for c in self.component_clusters.clusters],
            },
            "cross_file_duplicates": [d.to_dict() for d in self.cross_file_duplicates],
            "analysis_time_ms": self.analysis_time_ms,
            "total_styles_analyzed": self.total_styles_analyzed,
            "total_components_analyzed": self.total_components_analyzed,
        }


class CrossFileAnalyzer:
    """Analyzes fingerprints across entire repository for duplicates.

    Uses multi-signal similarity scoring and DBSCAN clustering to
    identify cross-file duplicates and near-duplicates.
    """

    def __init__(
        self,
        config: "UIQualityConfig",
        similarity_engine: SimilarityEngine | None = None,
    ):
        """Initialize the cross-file analyzer.

        Args:
            config: UI quality configuration.
            similarity_engine: Optional pre-configured similarity engine.
        """
        self.config = config
        self.similarity_engine = similarity_engine or SimilarityEngine(config)

        # Create clustering with thresholds from config
        near_dup_threshold = config.gating.similarity_thresholds.near_duplicate
        self.clustering = SimilarityClustering(
            similarity_engine=self.similarity_engine,
            min_cluster_size=2,
            eps=1 - near_dup_threshold,  # Convert similarity to distance
            min_samples=2,
        )

    def analyze_styles(
        self,
        all_styles: list["StyleFingerprint"],
    ) -> ClusteringResult:
        """Cluster styles from across the entire repo.

        Args:
            all_styles: List of all style fingerprints in the repo.

        Returns:
            ClusteringResult with style clusters.
        """
        if len(all_styles) < 2:
            return ClusteringResult(total_items=len(all_styles))

        return self.clustering.cluster_styles(all_styles)

    def analyze_components(
        self,
        all_components: list["StaticComponentFingerprint"],
        embeddings: list[list[float]] | None = None,
    ) -> ClusteringResult:
        """Cluster components from across the entire repo.

        Args:
            all_components: List of all component fingerprints in the repo.
            embeddings: Optional embeddings for components.

        Returns:
            ClusteringResult with component clusters.
        """
        if len(all_components) < 2:
            return ClusteringResult(total_items=len(all_components))

        return self.clustering.cluster_components(all_components, embeddings)

    def find_cross_file_duplicates(
        self,
        style_clusters: ClusteringResult,
        component_clusters: ClusteringResult,
        styles: list["StyleFingerprint"] | None = None,
        components: list["StaticComponentFingerprint"] | None = None,
    ) -> list[CrossFileDuplicate]:
        """Identify duplicates that span multiple files.

        Args:
            style_clusters: Clustering result for styles.
            component_clusters: Clustering result for components.
            styles: Original style fingerprints (for location info).
            components: Original component fingerprints (for location info).

        Returns:
            List of CrossFileDuplicate instances.
        """
        duplicates: list[CrossFileDuplicate] = []

        # Process style clusters
        for cluster in style_clusters.clusters:
            if cluster.size < 2:
                continue

            # Extract file locations from cluster item IDs
            file_locations = self._extract_unique_files(cluster.items)

            # Only report as cross-file if multiple files involved
            if len(file_locations) >= 2:
                duplicates.append(
                    CrossFileDuplicate(
                        duplicate_type="style",
                        cluster_id=cluster.cluster_id,
                        file_locations=cluster.items,  # file:line format
                        similarity_score=cluster.avg_internal_similarity,
                        recommended_action=self._recommend_action(cluster, "style"),
                        impact_estimate=self._estimate_impact(cluster),
                        details={
                            "cluster_size": cluster.size,
                            "representative": cluster.representative,
                            "unique_files": file_locations,
                        },
                    )
                )

        # Process component clusters
        for cluster in component_clusters.clusters:
            if cluster.size < 2:
                continue

            file_locations = self._extract_unique_files(cluster.items)

            if len(file_locations) >= 2:
                duplicates.append(
                    CrossFileDuplicate(
                        duplicate_type="component",
                        cluster_id=cluster.cluster_id,
                        file_locations=cluster.items,
                        similarity_score=cluster.avg_internal_similarity,
                        recommended_action=self._recommend_action(cluster, "component"),
                        impact_estimate=self._estimate_impact(cluster),
                        details={
                            "cluster_size": cluster.size,
                            "representative": cluster.representative,
                            "unique_files": file_locations,
                        },
                    )
                )

        # Sort by impact (high first) then by cluster size
        duplicates.sort(
            key=lambda d: (
                {"high": 0, "medium": 1, "low": 2}.get(d.impact_estimate, 1),
                -len(d.file_locations),
            )
        )

        return duplicates

    def run_full_analysis(
        self,
        styles: list["StyleFingerprint"],
        components: list["StaticComponentFingerprint"],
        embeddings: list[list[float]] | None = None,
    ) -> CrossFileClusterResult:
        """Run complete cross-file analysis.

        Args:
            styles: All style fingerprints.
            components: All component fingerprints.
            embeddings: Optional component embeddings.

        Returns:
            CrossFileClusterResult with all analysis data.
        """
        start_time = time.time()

        # Cluster styles
        style_clusters = self.analyze_styles(styles)

        # Cluster components
        component_clusters = self.analyze_components(components, embeddings)

        # Find cross-file duplicates
        cross_file_duplicates = self.find_cross_file_duplicates(
            style_clusters,
            component_clusters,
            styles,
            components,
        )

        analysis_time_ms = (time.time() - start_time) * 1000

        return CrossFileClusterResult(
            style_clusters=style_clusters,
            component_clusters=component_clusters,
            cross_file_duplicates=cross_file_duplicates,
            analysis_time_ms=analysis_time_ms,
            total_styles_analyzed=len(styles),
            total_components_analyzed=len(components),
        )

    def _extract_unique_files(self, items: list[str]) -> list[str]:
        """Extract unique file paths from item IDs.

        Item IDs are in format "file_path:line_number".

        Args:
            items: List of item IDs.

        Returns:
            List of unique file paths.
        """
        files = set()
        for item in items:
            if ":" in item:
                file_path = item.rsplit(":", 1)[0]
                files.add(file_path)
            else:
                files.add(item)
        return sorted(files)

    def _recommend_action(self, cluster: Cluster, duplicate_type: str) -> str:
        """Recommend action based on cluster characteristics.

        Args:
            cluster: The cluster to analyze.
            duplicate_type: "style" or "component".

        Returns:
            Recommended action string.
        """
        # High similarity with many instances -> consolidate
        if cluster.avg_internal_similarity > 0.95 and cluster.size >= 3:
            return "consolidate"

        # Perfect duplicates -> remove duplicates
        if cluster.avg_internal_similarity > 0.99:
            return "remove_duplicates"

        # Component with variants -> extract base
        if duplicate_type == "component" and cluster.size >= 3:
            return "extract_base"

        # Style duplicates -> create utility/token
        if duplicate_type == "style":
            return "create_utility"

        return "review"

    def _estimate_impact(self, cluster: Cluster) -> str:
        """Estimate impact of resolving a cluster.

        Args:
            cluster: The cluster to analyze.

        Returns:
            Impact estimate: "high", "medium", or "low".
        """
        # Many files affected -> high impact
        unique_files = self._extract_unique_files(cluster.items)

        if len(unique_files) >= 5 or cluster.size >= 10:
            return "high"
        elif len(unique_files) >= 3 or cluster.size >= 5:
            return "medium"
        else:
            return "low"


__all__ = [
    "CrossFileDuplicate",
    "CrossFileClusterResult",
    "CrossFileAnalyzer",
]
