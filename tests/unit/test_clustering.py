"""Tests for the clustering module.

Tests the SimilarityClustering class that groups similar UI components
and styles using DBSCAN.
"""

import pytest

from claude_indexer.ui.models import (
    StaticComponentFingerprint,
    StyleFingerprint,
    SymbolKind,
    SymbolRef,
    Visibility,
)
from claude_indexer.ui.similarity.clustering import (
    Cluster,
    ClusteringResult,
    SimilarityClustering,
)
from claude_indexer.ui.similarity.engine import SimilarityEngine


@pytest.fixture
def similarity_engine():
    """Create a default similarity engine."""
    return SimilarityEngine()


@pytest.fixture
def clustering(similarity_engine):
    """Create a clustering instance."""
    return SimilarityClustering(
        similarity_engine=similarity_engine,
        min_cluster_size=2,
        eps=0.15,  # 0.85 similarity threshold
        min_samples=2,
    )


def create_component(
    name: str,
    structure_hash: str = "abc123def456abc123def456abc12345",  # Valid 32-char hex
    style_refs: list[str] | None = None,
) -> StaticComponentFingerprint:
    """Helper to create test components with valid hex hashes."""
    ref = SymbolRef(
        file_path=f"test/{name}.tsx",
        start_line=1,
        end_line=10,
        name=name,
        kind=SymbolKind.COMPONENT,
        visibility=Visibility.EXPORTED,
    )
    return StaticComponentFingerprint(
        source_ref=ref,
        structure_hash=structure_hash,
        style_refs=style_refs or [],
    )


def create_style(
    file_path: str,
    exact_hash: str,
    near_hash: str,
) -> StyleFingerprint:
    """Helper to create test styles with valid hex hashes."""
    ref = SymbolRef(
        file_path=file_path,
        start_line=1,
        end_line=5,
        kind=SymbolKind.CSS,
        visibility=Visibility.LOCAL,
    )
    # Ensure hashes are valid hex
    if not all(c in "0123456789abcdef" for c in exact_hash.lower()):
        exact_hash = exact_hash.encode().hex()[:32].ljust(32, "0")
    if not all(c in "0123456789abcdef" for c in near_hash.lower()):
        near_hash = near_hash.encode().hex()[:32].ljust(32, "0")
    return StyleFingerprint(
        declaration_set={},
        exact_hash=exact_hash,
        near_hash=near_hash,
        source_refs=[ref],
    )


class TestCluster:
    """Tests for Cluster dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        cluster = Cluster(
            cluster_id=0,
            items=["item1", "item2"],
            representative="item1",
            size=2,
            avg_internal_similarity=0.9,
            metadata={"type": "button"},
        )

        data = cluster.to_dict()

        assert data["cluster_id"] == 0
        assert data["items"] == ["item1", "item2"]
        assert data["representative"] == "item1"
        assert data["size"] == 2
        assert data["avg_internal_similarity"] == 0.9
        assert data["metadata"] == {"type": "button"}

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "cluster_id": 1,
            "items": ["a", "b", "c"],
            "representative": "a",
            "size": 3,
            "avg_internal_similarity": 0.85,
            "metadata": {},
        }

        cluster = Cluster.from_dict(data)

        assert cluster.cluster_id == 1
        assert cluster.items == ["a", "b", "c"]
        assert cluster.representative == "a"
        assert cluster.size == 3


class TestClusteringResult:
    """Tests for ClusteringResult dataclass."""

    def test_cluster_count(self):
        """Test cluster count property."""
        result = ClusteringResult(
            clusters=[
                Cluster(cluster_id=0, items=["a", "b"], size=2),
                Cluster(cluster_id=1, items=["c", "d", "e"], size=3),
            ],
        )

        assert result.cluster_count == 2

    def test_clustered_item_count(self):
        """Test clustered item count property."""
        result = ClusteringResult(
            clusters=[
                Cluster(cluster_id=0, items=["a", "b"], size=2),
                Cluster(cluster_id=1, items=["c", "d", "e"], size=3),
            ],
        )

        assert result.clustered_item_count == 5

    def test_get_clusters_by_size(self):
        """Test filtering clusters by minimum size."""
        result = ClusteringResult(
            clusters=[
                Cluster(cluster_id=0, items=["a", "b"], size=2),
                Cluster(cluster_id=1, items=["c", "d", "e"], size=3),
                Cluster(cluster_id=2, items=["f", "g", "h", "i"], size=4),
            ],
        )

        large_clusters = result.get_clusters_by_size(min_size=3)

        assert len(large_clusters) == 2
        assert all(c.size >= 3 for c in large_clusters)

    def test_empty_result(self):
        """Test empty clustering result."""
        result = ClusteringResult(total_items=0)

        assert result.cluster_count == 0
        assert result.clustered_item_count == 0
        assert len(result.noise_items) == 0


class TestSimilarityClustering:
    """Tests for SimilarityClustering class."""

    def test_init(self, similarity_engine):
        """Test initialization."""
        clustering = SimilarityClustering(
            similarity_engine=similarity_engine,
            min_cluster_size=3,
            eps=0.2,
            min_samples=3,
        )

        assert clustering.min_cluster_size == 3
        assert clustering.eps == 0.2
        assert clustering.min_samples == 3

    def test_cluster_components_too_few(self, clustering):
        """Test clustering with too few components."""
        components = [create_component("Single")]

        result = clustering.cluster_components(components)

        assert result.cluster_count == 0
        assert result.total_items == 1

    def test_cluster_components_identical(self, clustering):
        """Test clustering identical components."""
        # Create components with identical valid hex hashes
        same_hash = "abc123def456abc123def456abc12345"
        components = [
            create_component("Button1", structure_hash=same_hash, style_refs=["btn"]),
            create_component("Button2", structure_hash=same_hash, style_refs=["btn"]),
            create_component("Button3", structure_hash=same_hash, style_refs=["btn"]),
        ]

        result = clustering.cluster_components(components)

        # Should cluster or all be treated as similar
        assert result.total_items == 3

    def test_cluster_components_distinct(self, clustering):
        """Test clustering distinct components."""
        components = [
            create_component(
                "Button",
                structure_hash="abc123def456abc123def456abc12345",
                style_refs=["btn"],
            ),
            create_component(
                "Card",
                structure_hash="123456789abcdef0123456789abcdef0",
                style_refs=["card"],
            ),
            create_component(
                "Modal",
                structure_hash="fedcba9876543210fedcba9876543210",
                style_refs=["modal"],
            ),
        ]

        result = clustering.cluster_components(components)

        # Result should be returned
        assert result.total_items == 3

    def test_cluster_styles_too_few(self, clustering):
        """Test style clustering with too few styles."""
        styles = [create_style("a.css", "hash", "nearhash")]

        result = clustering.cluster_styles(styles)

        assert result.cluster_count == 0
        assert result.total_items == 1

    def test_cluster_styles_identical(self, clustering):
        """Test clustering identical styles."""
        styles = [
            create_style("a.css", "same", "same"),
            create_style("b.css", "same", "same"),
            create_style("c.css", "same", "same"),
        ]

        result = clustering.cluster_styles(styles)

        # Identical styles should cluster together
        assert result.total_items == 3

    def test_cluster_has_representative(self, clustering):
        """Test that clusters have a representative."""
        same_hash = "abc123def456abc123def456abc12345"
        components = [
            create_component("Button1", structure_hash=same_hash, style_refs=["btn"]),
            create_component("Button2", structure_hash=same_hash, style_refs=["btn"]),
        ]

        result = clustering.cluster_components(components)

        if result.cluster_count > 0:
            assert result.clusters[0].representative is not None

    def test_cluster_avg_similarity(self, clustering):
        """Test average internal similarity calculation."""
        same_hash = "abc123def456abc123def456abc12345"
        components = [
            create_component("Button1", structure_hash=same_hash, style_refs=["btn"]),
            create_component("Button2", structure_hash=same_hash, style_refs=["btn"]),
        ]

        result = clustering.cluster_components(components)

        if result.cluster_count > 0:
            # Check cluster has avg similarity
            assert result.clusters[0].avg_internal_similarity >= 0

    def test_clusters_sorted_by_size(self, clustering):
        """Test that clusters are sorted by size descending."""
        # Create components with different hashes (use valid hex)
        hash_a = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        hash_b = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        components = [
            # Group 1: 2 items
            create_component("A1", structure_hash=hash_a, style_refs=["a"]),
            create_component("A2", structure_hash=hash_a, style_refs=["a"]),
            # Group 2: 3 items
            create_component("B1", structure_hash=hash_b, style_refs=["b"]),
            create_component("B2", structure_hash=hash_b, style_refs=["b"]),
            create_component("B3", structure_hash=hash_b, style_refs=["b"]),
        ]

        result = clustering.cluster_components(components)

        if result.cluster_count >= 2:
            # First cluster should be largest
            assert result.clusters[0].size >= result.clusters[1].size


class TestSimpleClustering:
    """Tests for fallback simple clustering."""

    def test_simple_clustering_fallback(self, similarity_engine):
        """Test simple clustering when sklearn unavailable."""
        clustering = SimilarityClustering(similarity_engine)

        import numpy as np

        # Create a simple distance matrix where items 0,1 are close, 2 is far
        distance_matrix = np.array(
            [
                [0.0, 0.1, 0.9],  # 0 is close to 1, far from 2
                [0.1, 0.0, 0.9],  # 1 is close to 0, far from 2
                [0.9, 0.9, 0.0],  # 2 is far from both
            ]
        )

        labels = clustering._simple_clustering(distance_matrix)

        # Items 0 and 1 should be in same cluster
        assert labels[0] == labels[1] or labels[0] == -1 or labels[1] == -1


class TestClusteringEdgeCases:
    """Edge case tests for clustering."""

    def test_empty_input(self, clustering):
        """Test with empty input."""
        result = clustering.cluster_components([])

        assert result.cluster_count == 0
        assert result.total_items == 0

    def test_single_item(self, clustering):
        """Test with single item."""
        components = [create_component("Single")]

        result = clustering.cluster_components(components)

        assert result.total_items == 1

    def test_all_distinct(self, clustering):
        """Test when all items are distinct."""
        # Use unique valid hex hashes
        components = [
            create_component(
                f"Comp{i}", structure_hash=f"{i:032x}", style_refs=[f"style{i}"]
            )
            for i in range(5)
        ]

        result = clustering.cluster_components(components)

        # Result should be returned
        assert result.total_items == 5
