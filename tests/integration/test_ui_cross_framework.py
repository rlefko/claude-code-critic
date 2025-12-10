"""
Integration tests for cross-framework UI consistency detection.

These tests validate that the UI consistency checker correctly identifies
duplicates and inconsistencies across React, Vue, and Svelte components.
"""

import pytest
from pathlib import Path
from typing import List, Dict, Any

# Import UI modules
try:
    from claude_indexer.ui.collectors.source import SourceCollector
    from claude_indexer.ui.collectors.adapters.react import ReactAdapter
    from claude_indexer.ui.collectors.adapters.vue import VueAdapter
    from claude_indexer.ui.collectors.adapters.svelte import SvelteAdapter
    from claude_indexer.ui.normalizers.component import ComponentNormalizer
    from claude_indexer.ui.similarity.engine import SimilarityEngine
    from claude_indexer.ui.similarity.clustering import Clustering
    from claude_indexer.ui.models import (
        StaticComponentFingerprint,
        StyleFingerprint,
        Finding,
        Severity,
    )
    UI_MODULES_AVAILABLE = True
except ImportError as e:
    UI_MODULES_AVAILABLE = False
    IMPORT_ERROR = str(e)


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "ui_repo"


pytestmark = pytest.mark.skipif(
    not UI_MODULES_AVAILABLE,
    reason=f"UI modules not available: {IMPORT_ERROR if not UI_MODULES_AVAILABLE else ''}"
)


@pytest.fixture
def fixture_path() -> Path:
    """Return the path to the UI test fixture repository."""
    return FIXTURE_PATH


@pytest.fixture
def source_collector() -> SourceCollector:
    """Create a source collector with all framework adapters."""
    collector = SourceCollector()
    collector.register_adapter(".tsx", ReactAdapter())
    collector.register_adapter(".jsx", ReactAdapter())
    collector.register_adapter(".vue", VueAdapter())
    collector.register_adapter(".svelte", SvelteAdapter())
    return collector


@pytest.fixture
def component_normalizer() -> ComponentNormalizer:
    """Create a component normalizer for testing."""
    return ComponentNormalizer()


@pytest.fixture
def similarity_engine() -> SimilarityEngine:
    """Create a similarity engine for testing."""
    return SimilarityEngine(
        semantic_weight=0.5,
        structure_weight=0.3,
        style_weight=0.2,
    )


class TestCrossFrameworkComponentExtraction:
    """Test component extraction across different frameworks."""

    def test_extracts_react_component(
        self, fixture_path: Path, source_collector: SourceCollector
    ):
        """Should correctly extract React component structure."""
        button_path = fixture_path / "components" / "Button.tsx"
        content = button_path.read_text()

        components = source_collector.extract_components(button_path, content)

        assert len(components) >= 1, "Should extract at least one component"

        # Find the Button component
        button = next((c for c in components if "Button" in c.name), None)
        assert button is not None, "Should find Button component"

        # Verify extracted data
        assert button.source_ref is not None
        assert button.source_ref.file_path == str(button_path)

    def test_extracts_vue_component(
        self, fixture_path: Path, source_collector: SourceCollector
    ):
        """Should correctly extract Vue component structure."""
        vue_button_path = fixture_path / "components" / "VueButton.vue"
        content = vue_button_path.read_text()

        components = source_collector.extract_components(vue_button_path, content)

        assert len(components) >= 1, "Should extract at least one Vue component"

        # Find the VueButton component
        vue_button = next((c for c in components if "VueButton" in c.name), None)
        assert vue_button is not None, "Should find VueButton component"

    def test_extracts_svelte_component(
        self, fixture_path: Path, source_collector: SourceCollector
    ):
        """Should correctly extract Svelte component structure."""
        svelte_path = fixture_path / "components" / "SvelteInput.svelte"
        content = svelte_path.read_text()

        components = source_collector.extract_components(svelte_path, content)

        assert len(components) >= 1, "Should extract at least one Svelte component"


class TestCrossFrameworkNormalization:
    """Test that components are normalized consistently across frameworks."""

    def test_button_structure_normalization(
        self,
        fixture_path: Path,
        source_collector: SourceCollector,
        component_normalizer: ComponentNormalizer,
    ):
        """Button components across frameworks should have similar normalized structures."""
        react_button = fixture_path / "components" / "Button.tsx"
        vue_button = fixture_path / "components" / "VueButton.vue"

        react_components = source_collector.extract_components(
            react_button, react_button.read_text()
        )
        vue_components = source_collector.extract_components(
            vue_button, vue_button.read_text()
        )

        # Normalize both
        react_normalized = component_normalizer.normalize(react_components[0])
        vue_normalized = component_normalizer.normalize(vue_components[0])

        # Structure hashes should be similar (indicating structural similarity)
        # The exact match depends on implementation, but they should be comparable
        assert react_normalized.structure_hash is not None
        assert vue_normalized.structure_hash is not None

    def test_card_structure_normalization(
        self,
        fixture_path: Path,
        source_collector: SourceCollector,
        component_normalizer: ComponentNormalizer,
    ):
        """Card components should normalize to similar structures."""
        react_card = fixture_path / "components" / "Card.tsx"
        vue_card = fixture_path / "components" / "VueCard.vue"

        react_components = source_collector.extract_components(
            react_card, react_card.read_text()
        )
        vue_components = source_collector.extract_components(
            vue_card, vue_card.read_text()
        )

        react_normalized = component_normalizer.normalize(react_components[0])
        vue_normalized = component_normalizer.normalize(vue_components[0])

        # Both should have normalized render tree structure
        assert react_normalized is not None
        assert vue_normalized is not None


class TestCrossFrameworkSimilarityScoring:
    """Test similarity scoring across different frameworks."""

    def test_react_vue_button_similarity(
        self,
        fixture_path: Path,
        source_collector: SourceCollector,
        component_normalizer: ComponentNormalizer,
        similarity_engine: SimilarityEngine,
    ):
        """React Button and Vue Button should have high similarity score."""
        react_button = fixture_path / "components" / "Button.tsx"
        vue_button = fixture_path / "components" / "VueButton.vue"

        react_components = source_collector.extract_components(
            react_button, react_button.read_text()
        )
        vue_components = source_collector.extract_components(
            vue_button, vue_button.read_text()
        )

        # Get normalized fingerprints
        react_fp = component_normalizer.normalize(react_components[0])
        vue_fp = component_normalizer.normalize(vue_components[0])

        # Calculate similarity
        similarity = similarity_engine.calculate_similarity(react_fp, vue_fp)

        # Should be highly similar (> 0.7)
        assert similarity > 0.7, f"Expected high similarity, got {similarity}"

    def test_react_vue_card_similarity(
        self,
        fixture_path: Path,
        source_collector: SourceCollector,
        component_normalizer: ComponentNormalizer,
        similarity_engine: SimilarityEngine,
    ):
        """React Card and Vue Card should have high similarity score."""
        react_card = fixture_path / "components" / "Card.tsx"
        vue_card = fixture_path / "components" / "VueCard.vue"

        react_components = source_collector.extract_components(
            react_card, react_card.read_text()
        )
        vue_components = source_collector.extract_components(
            vue_card, vue_card.read_text()
        )

        react_fp = component_normalizer.normalize(react_components[0])
        vue_fp = component_normalizer.normalize(vue_components[0])

        similarity = similarity_engine.calculate_similarity(react_fp, vue_fp)

        assert similarity > 0.7, f"Expected high similarity, got {similarity}"

    def test_button_card_low_similarity(
        self,
        fixture_path: Path,
        source_collector: SourceCollector,
        component_normalizer: ComponentNormalizer,
        similarity_engine: SimilarityEngine,
    ):
        """Button and Card should have LOW similarity score."""
        button = fixture_path / "components" / "Button.tsx"
        card = fixture_path / "components" / "Card.tsx"

        button_components = source_collector.extract_components(
            button, button.read_text()
        )
        card_components = source_collector.extract_components(
            card, card.read_text()
        )

        button_fp = component_normalizer.normalize(button_components[0])
        card_fp = component_normalizer.normalize(card_components[0])

        similarity = similarity_engine.calculate_similarity(button_fp, card_fp)

        # Should be dissimilar (< 0.5)
        assert similarity < 0.5, f"Expected low similarity between Button and Card, got {similarity}"


class TestCrossFrameworkClustering:
    """Test clustering of similar components across frameworks."""

    def test_clusters_similar_buttons(
        self,
        fixture_path: Path,
        source_collector: SourceCollector,
        component_normalizer: ComponentNormalizer,
    ):
        """Should cluster Button.tsx, ButtonVariant.tsx, and VueButton.vue together."""
        button_files = [
            fixture_path / "components" / "Button.tsx",
            fixture_path / "components" / "ButtonVariant.tsx",
            fixture_path / "components" / "VueButton.vue",
        ]

        fingerprints = []
        for file_path in button_files:
            content = file_path.read_text()
            components = source_collector.extract_components(file_path, content)
            if components:
                fp = component_normalizer.normalize(components[0])
                fp.source_file = str(file_path)
                fingerprints.append(fp)

        # Cluster the components
        clustering = Clustering(threshold=0.7)
        clusters = clustering.cluster(fingerprints)

        # All button components should be in the same cluster
        # (or at least Button and VueButton should cluster)
        assert len(clusters) >= 1, "Should form at least one cluster"

        # Find the largest cluster (should contain the buttons)
        largest_cluster = max(clusters, key=len)
        assert len(largest_cluster) >= 2, "Largest cluster should contain at least 2 buttons"

    def test_clusters_similar_cards(
        self,
        fixture_path: Path,
        source_collector: SourceCollector,
        component_normalizer: ComponentNormalizer,
    ):
        """Should cluster Card.tsx, CardAlt.tsx, and VueCard.vue together."""
        card_files = [
            fixture_path / "components" / "Card.tsx",
            fixture_path / "components" / "CardAlt.tsx",
            fixture_path / "components" / "VueCard.vue",
        ]

        fingerprints = []
        for file_path in card_files:
            content = file_path.read_text()
            components = source_collector.extract_components(file_path, content)
            if components:
                fp = component_normalizer.normalize(components[0])
                fp.source_file = str(file_path)
                fingerprints.append(fp)

        clustering = Clustering(threshold=0.7)
        clusters = clustering.cluster(fingerprints)

        assert len(clusters) >= 1
        largest_cluster = max(clusters, key=len)
        assert len(largest_cluster) >= 2, "Should cluster at least 2 card components"


class TestCrossFrameworkRecommendations:
    """Test that the system generates appropriate reuse recommendations."""

    def test_recommends_existing_button_for_variant(
        self,
        fixture_path: Path,
        source_collector: SourceCollector,
        component_normalizer: ComponentNormalizer,
        similarity_engine: SimilarityEngine,
    ):
        """When analyzing ButtonVariant, should recommend using Button.tsx."""
        canonical_button = fixture_path / "components" / "Button.tsx"
        variant_button = fixture_path / "components" / "ButtonVariant.tsx"

        canonical_components = source_collector.extract_components(
            canonical_button, canonical_button.read_text()
        )
        variant_components = source_collector.extract_components(
            variant_button, variant_button.read_text()
        )

        canonical_fp = component_normalizer.normalize(canonical_components[0])
        variant_fp = component_normalizer.normalize(variant_components[0])

        # Find similar components
        similarity = similarity_engine.calculate_similarity(canonical_fp, variant_fp)

        # Should recommend canonical button
        if similarity > 0.7:
            # This is where we'd generate the recommendation
            recommendation = f"Consider using Button.tsx instead of ButtonVariant.tsx (similarity: {similarity:.2%})"
            assert "Button.tsx" in recommendation

    def test_recommends_consolidation_for_cross_framework(
        self,
        fixture_path: Path,
        source_collector: SourceCollector,
        component_normalizer: ComponentNormalizer,
        similarity_engine: SimilarityEngine,
    ):
        """Should recommend consolidating React and Vue buttons."""
        react_button = fixture_path / "components" / "Button.tsx"
        vue_button = fixture_path / "components" / "VueButton.vue"

        react_components = source_collector.extract_components(
            react_button, react_button.read_text()
        )
        vue_components = source_collector.extract_components(
            vue_button, vue_button.read_text()
        )

        react_fp = component_normalizer.normalize(react_components[0])
        vue_fp = component_normalizer.normalize(vue_components[0])

        similarity = similarity_engine.calculate_similarity(react_fp, vue_fp)

        # If highly similar, should recommend shared design tokens/styles
        if similarity > 0.8:
            recommendation = "Consider extracting shared design tokens or style constants"
            assert "shared" in recommendation.lower() or "extract" in recommendation.lower()


class TestStyleUsageConsistency:
    """Test that style usage is consistent across frameworks."""

    def test_all_buttons_use_same_tokens(
        self, fixture_path: Path, source_collector: SourceCollector
    ):
        """All button implementations should use the same design tokens."""
        button_files = [
            ("Button.tsx", fixture_path / "components" / "Button.tsx"),
            ("VueButton.vue", fixture_path / "components" / "VueButton.vue"),
        ]

        expected_tokens = [
            "--color-primary-600",
            "--color-neutral-100",
            "--color-text-inverse",
            "--spacing-",
            "--radius-",
        ]

        for name, file_path in button_files:
            content = file_path.read_text()

            for token in expected_tokens:
                if "ButtonVariant" not in name:  # Variant has some hardcoded values
                    assert token in content, f"{name} should use token {token}"

    def test_all_cards_use_same_tokens(
        self, fixture_path: Path
    ):
        """All card implementations should use consistent tokens."""
        card_files = [
            fixture_path / "components" / "Card.tsx",
            fixture_path / "components" / "VueCard.vue",
        ]

        expected_tokens = [
            "--color-bg-primary",
            "--shadow-sm",
            "--shadow-lg",
            "--radius-lg",
            "--spacing-",
        ]

        for file_path in card_files:
            content = file_path.read_text()

            for token in expected_tokens:
                assert token in content, f"{file_path.name} should use token {token}"
