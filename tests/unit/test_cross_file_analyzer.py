"""Unit tests for cross-file analysis."""

import pytest

from claude_indexer.ui.ci.cross_file_analyzer import (
    CrossFileAnalyzer,
    CrossFileClusterResult,
    CrossFileDuplicate,
)
from claude_indexer.ui.config import UIQualityConfig
from claude_indexer.ui.models import (
    StaticComponentFingerprint,
    StyleFingerprint,
    SymbolKind,
    SymbolRef,
)
from claude_indexer.ui.similarity.clustering import Cluster, ClusteringResult


class TestCrossFileDuplicate:
    """Tests for CrossFileDuplicate dataclass."""

    def test_create_cross_file_duplicate(self):
        """Test basic CrossFileDuplicate creation."""
        dup = CrossFileDuplicate(
            duplicate_type="style",
            cluster_id=1,
            file_locations=["file1.tsx:10", "file2.tsx:20"],
            similarity_score=0.95,
            recommended_action="consolidate",
            impact_estimate="high",
        )

        assert dup.duplicate_type == "style"
        assert dup.cluster_id == 1
        assert len(dup.file_locations) == 2
        assert dup.similarity_score == 0.95
        assert dup.recommended_action == "consolidate"
        assert dup.impact_estimate == "high"

    def test_cross_file_duplicate_to_dict(self):
        """Test CrossFileDuplicate serialization."""
        dup = CrossFileDuplicate(
            duplicate_type="component",
            cluster_id=2,
            file_locations=["a.tsx:1", "b.tsx:2", "c.tsx:3"],
            similarity_score=0.88,
            details={"cluster_size": 3},
        )

        data = dup.to_dict()

        assert data["duplicate_type"] == "component"
        assert data["cluster_id"] == 2
        assert len(data["file_locations"]) == 3
        assert data["details"]["cluster_size"] == 3

    def test_cross_file_duplicate_from_dict(self):
        """Test CrossFileDuplicate deserialization."""
        data = {
            "duplicate_type": "style",
            "cluster_id": 5,
            "file_locations": ["x.tsx:10"],
            "similarity_score": 0.9,
            "recommended_action": "extract",
            "impact_estimate": "medium",
            "details": {"representative": "x.tsx:10"},
        }

        dup = CrossFileDuplicate.from_dict(data)

        assert dup.duplicate_type == "style"
        assert dup.cluster_id == 5
        assert dup.recommended_action == "extract"
        assert dup.details["representative"] == "x.tsx:10"


class TestCrossFileClusterResult:
    """Tests for CrossFileClusterResult dataclass."""

    def test_create_cluster_result(self):
        """Test basic CrossFileClusterResult creation."""
        result = CrossFileClusterResult(
            total_styles_analyzed=100,
            total_components_analyzed=50,
            analysis_time_ms=150.5,
        )

        assert result.total_styles_analyzed == 100
        assert result.total_components_analyzed == 50
        assert result.analysis_time_ms == 150.5
        assert result.duplicate_count == 0

    def test_cluster_result_with_duplicates(self):
        """Test CrossFileClusterResult with duplicates."""
        dup1 = CrossFileDuplicate(
            duplicate_type="style",
            cluster_id=1,
            file_locations=["a.tsx:1", "b.tsx:2"],
            similarity_score=0.95,
            impact_estimate="high",
        )
        dup2 = CrossFileDuplicate(
            duplicate_type="component",
            cluster_id=2,
            file_locations=["c.tsx:1", "d.tsx:2"],
            similarity_score=0.88,
            impact_estimate="medium",
        )

        result = CrossFileClusterResult(
            cross_file_duplicates=[dup1, dup2],
        )

        assert result.duplicate_count == 2
        high_impact = result.get_high_impact_duplicates()
        assert len(high_impact) == 1
        assert high_impact[0].duplicate_type == "style"

    def test_cluster_result_counts(self):
        """Test cluster count properties."""
        style_clusters = ClusteringResult(
            clusters=[
                Cluster(cluster_id=0, items=["a:1", "b:2"], size=2),
                Cluster(cluster_id=1, items=["c:3", "d:4"], size=2),
            ],
            total_items=10,
        )
        component_clusters = ClusteringResult(
            clusters=[Cluster(cluster_id=0, items=["x:1", "y:2", "z:3"], size=3)],
            total_items=5,
        )

        result = CrossFileClusterResult(
            style_clusters=style_clusters,
            component_clusters=component_clusters,
        )

        assert result.style_cluster_count == 2
        assert result.component_cluster_count == 1

    def test_cluster_result_to_dict(self):
        """Test CrossFileClusterResult serialization."""
        dup = CrossFileDuplicate(
            duplicate_type="style",
            cluster_id=1,
            file_locations=["a:1", "b:2"],
        )

        result = CrossFileClusterResult(
            cross_file_duplicates=[dup],
            analysis_time_ms=100.0,
            total_styles_analyzed=20,
            total_components_analyzed=10,
        )

        data = result.to_dict()

        assert data["analysis_time_ms"] == 100.0
        assert data["total_styles_analyzed"] == 20
        assert len(data["cross_file_duplicates"]) == 1


class TestCrossFileAnalyzer:
    """Tests for CrossFileAnalyzer class."""

    @pytest.fixture
    def config(self):
        """Create a test UI quality config."""
        return UIQualityConfig()

    @pytest.fixture
    def analyzer(self, config):
        """Create a CrossFileAnalyzer instance."""
        return CrossFileAnalyzer(config)

    def test_analyze_empty_styles(self, analyzer):
        """Test analyzing empty style list."""
        result = analyzer.analyze_styles([])

        assert result.cluster_count == 0
        assert result.total_items == 0

    def test_analyze_single_style(self, analyzer):
        """Test analyzing single style (no clustering)."""
        style = StyleFingerprint(
            declaration_set={"color": "#333"},
            exact_hash="abc123",
            near_hash="def456",
            source_refs=[
                SymbolRef(
                    file_path="test.tsx",
                    start_line=10,
                    end_line=10,
                    kind=SymbolKind.CSS,
                )
            ],
        )

        result = analyzer.analyze_styles([style])

        assert result.total_items == 1
        assert result.cluster_count == 0  # Need at least 2 for clustering

    def test_analyze_duplicate_styles(self, analyzer):
        """Test analyzing duplicate styles."""
        # Create identical styles from different files
        style1 = StyleFingerprint(
            declaration_set={"color": "#333", "padding": "8px"},
            exact_hash="same_hash",
            near_hash="same_near",
            source_refs=[
                SymbolRef(
                    file_path="file1.tsx",
                    start_line=10,
                    end_line=15,
                    kind=SymbolKind.CSS,
                )
            ],
        )
        style2 = StyleFingerprint(
            declaration_set={"color": "#333", "padding": "8px"},
            exact_hash="same_hash",
            near_hash="same_near",
            source_refs=[
                SymbolRef(
                    file_path="file2.tsx",
                    start_line=20,
                    end_line=25,
                    kind=SymbolKind.CSS,
                )
            ],
        )

        result = analyzer.analyze_styles([style1, style2])

        # Should find a cluster with these duplicates
        assert result.total_items == 2

    def test_analyze_empty_components(self, analyzer):
        """Test analyzing empty component list."""
        result = analyzer.analyze_components([])

        assert result.cluster_count == 0
        assert result.total_items == 0

    def test_analyze_single_component(self, analyzer):
        """Test analyzing single component."""
        component = StaticComponentFingerprint(
            structure_hash="struct123",
            style_refs=["btn"],
            source_ref=SymbolRef(
                file_path="Button.tsx",
                start_line=1,
                end_line=50,
                kind=SymbolKind.COMPONENT,
                name="Button",
            ),
        )

        result = analyzer.analyze_components([component])

        assert result.total_items == 1
        assert result.cluster_count == 0

    def test_extract_unique_files(self, analyzer):
        """Test extracting unique files from item IDs."""
        items = [
            "file1.tsx:10",
            "file1.tsx:20",
            "file2.tsx:30",
            "file3.tsx:40",
        ]

        files = analyzer._extract_unique_files(items)

        assert len(files) == 3
        assert "file1.tsx" in files
        assert "file2.tsx" in files
        assert "file3.tsx" in files

    def test_extract_unique_files_no_line_number(self, analyzer):
        """Test extracting files without line numbers."""
        items = ["file1.tsx", "file2.tsx"]

        files = analyzer._extract_unique_files(items)

        assert len(files) == 2

    def test_recommend_action_consolidate(self, analyzer):
        """Test action recommendation for consolidation."""
        cluster = Cluster(
            cluster_id=0,
            items=["a:1", "b:2", "c:3", "d:4"],  # 4 items
            size=4,  # Must set size explicitly
            avg_internal_similarity=0.97,  # > 0.95
        )

        action = analyzer._recommend_action(cluster, "style")

        # High similarity with many instances -> consolidate
        assert action == "consolidate"

    def test_recommend_action_remove_duplicates(self, analyzer):
        """Test action recommendation for removing duplicates."""
        cluster = Cluster(
            cluster_id=0,
            items=["a:1", "b:2"],
            size=2,
            avg_internal_similarity=0.995,
        )

        action = analyzer._recommend_action(cluster, "style")

        assert action == "remove_duplicates"

    def test_recommend_action_extract_base(self, analyzer):
        """Test action recommendation for extracting base."""
        cluster = Cluster(
            cluster_id=0,
            items=["a:1", "b:2", "c:3", "d:4"],  # >= 3 items
            size=4,  # Must set size explicitly
            avg_internal_similarity=0.80,  # Not triggering consolidate
        )

        action = analyzer._recommend_action(cluster, "component")

        # Component with variants -> extract base
        assert action == "extract_base"

    def test_recommend_action_create_utility(self, analyzer):
        """Test action recommendation for creating utility."""
        cluster = Cluster(
            cluster_id=0,
            items=["a:1", "b:2"],
            size=2,
            avg_internal_similarity=0.85,
        )

        action = analyzer._recommend_action(cluster, "style")

        assert action == "create_utility"

    def test_estimate_impact_high(self, analyzer):
        """Test high impact estimation."""
        cluster = Cluster(
            cluster_id=0,
            items=[f"file{i}.tsx:1" for i in range(10)],  # 10 items
            size=10,
        )

        impact = analyzer._estimate_impact(cluster)

        assert impact == "high"

    def test_estimate_impact_medium(self, analyzer):
        """Test medium impact estimation."""
        cluster = Cluster(
            cluster_id=0,
            items=["file1.tsx:1", "file2.tsx:2", "file3.tsx:3", "file4.tsx:4"],
            size=4,
        )

        impact = analyzer._estimate_impact(cluster)

        assert impact == "medium"

    def test_estimate_impact_low(self, analyzer):
        """Test low impact estimation."""
        cluster = Cluster(
            cluster_id=0,
            items=["file1.tsx:1", "file2.tsx:2"],
            size=2,
        )

        impact = analyzer._estimate_impact(cluster)

        assert impact == "low"

    def test_find_cross_file_duplicates_single_file(self, analyzer):
        """Test that single-file clusters are not reported as cross-file."""
        cluster = Cluster(
            cluster_id=0,
            items=["same_file.tsx:10", "same_file.tsx:20"],  # Same file
            size=2,
            avg_internal_similarity=0.95,
        )
        cluster.representative = "same_file.tsx:10"

        style_clusters = ClusteringResult(
            clusters=[cluster],
            total_items=2,
        )

        duplicates = analyzer.find_cross_file_duplicates(
            style_clusters,
            ClusteringResult(),
        )

        # Should not be reported as cross-file duplicate (same file)
        assert len(duplicates) == 0

    def test_find_cross_file_duplicates_multiple_files(self, analyzer):
        """Test finding cross-file duplicates."""
        # Create a cluster with items from multiple files (size >= 2 required)
        cluster = Cluster(
            cluster_id=0,
            items=["file1.tsx:10", "file2.tsx:20", "file3.tsx:30"],
            size=3,  # Must set size explicitly
            avg_internal_similarity=0.92,
        )
        cluster.representative = "file1.tsx:10"

        style_clusters = ClusteringResult(
            clusters=[cluster],
            total_items=3,
        )

        duplicates = analyzer.find_cross_file_duplicates(
            style_clusters,
            ClusteringResult(),
        )

        # Should find 1 cross-file duplicate (3 files involved)
        assert len(duplicates) == 1
        assert duplicates[0].duplicate_type == "style"
        assert len(duplicates[0].file_locations) == 3

    def test_run_full_analysis(self, analyzer):
        """Test running full cross-file analysis."""
        styles = [
            StyleFingerprint(
                declaration_set={"color": "#333"},
                exact_hash="hash1",
                near_hash="near1",
                source_refs=[
                    SymbolRef("file1.tsx", 10, 15, SymbolKind.CSS)
                ],
            ),
            StyleFingerprint(
                declaration_set={"color": "#333"},
                exact_hash="hash1",
                near_hash="near1",
                source_refs=[
                    SymbolRef("file2.tsx", 20, 25, SymbolKind.CSS)
                ],
            ),
        ]

        components = [
            StaticComponentFingerprint(
                structure_hash="struct1",
                style_refs=["btn"],
                source_ref=SymbolRef("Button.tsx", 1, 50, SymbolKind.COMPONENT),
            ),
        ]

        result = analyzer.run_full_analysis(styles, components)

        assert result.total_styles_analyzed == 2
        assert result.total_components_analyzed == 1
        assert result.analysis_time_ms > 0

    def test_duplicates_sorted_by_impact(self, analyzer):
        """Test that duplicates are sorted by impact."""
        # Low impact cluster (2 different files)
        low_cluster = Cluster(
            cluster_id=0,
            items=["a1.tsx:1", "b1.tsx:2"],
            size=2,  # Must set size explicitly
            avg_internal_similarity=0.9,
        )
        low_cluster.representative = "a1.tsx:1"

        # High impact cluster (10 different files)
        high_items = [f"f{i}.tsx:{i}" for i in range(10)]
        high_cluster = Cluster(
            cluster_id=1,
            items=high_items,
            size=10,  # Must set size explicitly
            avg_internal_similarity=0.9,
        )
        high_cluster.representative = "f0.tsx:0"

        style_clusters = ClusteringResult(
            clusters=[low_cluster, high_cluster],
            total_items=12,
        )

        duplicates = analyzer.find_cross_file_duplicates(
            style_clusters,
            ClusteringResult(),
        )

        # High impact should come first
        assert len(duplicates) == 2
        assert duplicates[0].impact_estimate == "high"
        assert duplicates[1].impact_estimate == "low"
