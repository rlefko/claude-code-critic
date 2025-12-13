"""Tests for the similarity engine module.

Tests the SimilarityEngine class that computes multi-signal
similarity scores and classifications.
"""

import pytest

from claude_indexer.ui.config import UIQualityConfig
from claude_indexer.ui.models import (
    StaticComponentFingerprint,
    StyleFingerprint,
    SymbolKind,
    SymbolRef,
    Visibility,
)
from claude_indexer.ui.similarity.engine import (
    SimilarityClassification,
    SimilarityEngine,
    SimilarityEngineConfig,
    SimilarityResult,
)


@pytest.fixture
def engine():
    """Create a default similarity engine."""
    return SimilarityEngine()


@pytest.fixture
def config_engine():
    """Create a similarity engine with config."""
    config = UIQualityConfig()
    return SimilarityEngine(config=config)


def create_component(
    name: str,
    structure_hash: str = "abc123def456abc123def456abc12345",  # Valid 32-char hex
    style_refs: list[str] | None = None,
    embedding_id: str | None = None,
) -> StaticComponentFingerprint:
    """Helper to create test components."""
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
        embedding_id=embedding_id,
    )


def create_style(
    file_path: str,
    exact_hash: str,
    near_hash: str,
    declarations: dict[str, str] | None = None,
) -> StyleFingerprint:
    """Helper to create test styles with valid hex hashes."""
    ref = SymbolRef(
        file_path=file_path,
        start_line=1,
        end_line=5,
        kind=SymbolKind.CSS,
        visibility=Visibility.LOCAL,
    )
    # Ensure hashes are valid hex by padding if needed
    if not all(c in "0123456789abcdef" for c in exact_hash.lower()):
        exact_hash = exact_hash.encode().hex()[:32].ljust(32, "0")
    if not all(c in "0123456789abcdef" for c in near_hash.lower()):
        near_hash = near_hash.encode().hex()[:32].ljust(32, "0")
    return StyleFingerprint(
        declaration_set=declarations or {},
        exact_hash=exact_hash,
        near_hash=near_hash,
        source_refs=[ref],
    )


class TestSimilarityResult:
    """Tests for SimilarityResult dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = SimilarityResult(
            source_id="comp1",
            target_id="comp2",
            semantic_score=0.8,
            structural_score=0.9,
            style_score=0.7,
            combined_score=0.82,
            classification=SimilarityClassification.NEAR_DUPLICATE,
        )

        data = result.to_dict()

        assert data["source_id"] == "comp1"
        assert data["target_id"] == "comp2"
        assert data["semantic_score"] == 0.8
        assert data["structural_score"] == 0.9
        assert data["style_score"] == 0.7
        assert data["combined_score"] == 0.82
        assert data["classification"] == "near_duplicate"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "source_id": "comp1",
            "target_id": "comp2",
            "semantic_score": 0.8,
            "structural_score": 0.9,
            "style_score": 0.7,
            "combined_score": 0.82,
            "classification": "near_duplicate",
        }

        result = SimilarityResult.from_dict(data)

        assert result.source_id == "comp1"
        assert result.target_id == "comp2"
        assert result.semantic_score == 0.8
        assert result.classification == SimilarityClassification.NEAR_DUPLICATE


class TestSimilarityEngineConfig:
    """Tests for SimilarityEngineConfig."""

    def test_default_weights(self):
        """Test default weight configuration."""
        config = SimilarityEngineConfig()

        assert config.semantic_weight == 0.5
        assert config.structural_weight == 0.3
        assert config.style_weight == 0.2

    def test_default_thresholds(self):
        """Test default threshold configuration."""
        config = SimilarityEngineConfig()

        assert config.duplicate_threshold == 0.95
        assert config.near_duplicate_threshold == 0.80
        assert config.similar_threshold == 0.60


class TestSimilarityEngine:
    """Tests for SimilarityEngine class."""

    def test_init_default(self):
        """Test default initialization."""
        engine = SimilarityEngine()

        assert engine.config is None
        assert engine.engine_config is not None
        assert engine.engine_config.semantic_weight == 0.5

    def test_init_with_config(self):
        """Test initialization with UIQualityConfig."""
        config = UIQualityConfig()
        engine = SimilarityEngine(config=config)

        # Should use thresholds from config
        assert (
            engine.engine_config.duplicate_threshold
            == config.gating.similarity_thresholds.duplicate
        )
        assert (
            engine.engine_config.near_duplicate_threshold
            == config.gating.similarity_thresholds.near_duplicate
        )

    def test_compute_component_similarity_identical(self, engine):
        """Test similarity between identical components."""
        # Use same valid hex hash
        same_hash = "abc123def456abc123def456abc12345"
        comp1 = create_component(
            "Button", structure_hash=same_hash, style_refs=["btn", "primary"]
        )
        comp2 = create_component(
            "Button2", structure_hash=same_hash, style_refs=["btn", "primary"]
        )

        result = engine.compute_component_similarity(comp1, comp2)

        assert result.structural_score == 1.0
        assert result.style_score == 1.0
        # Combined = 0.5*0 + 0.3*1 + 0.2*1 = 0.5 (no embeddings provided)
        assert result.combined_score == 0.5

    def test_compute_component_similarity_different(self, engine):
        """Test similarity between different components."""
        comp1 = create_component(
            "Button",
            structure_hash="abc123def456abc123def456abc12345",
            style_refs=["btn"],
        )
        comp2 = create_component(
            "Card",
            structure_hash="123456789abcdef0123456789abcdef0",
            style_refs=["card"],
        )

        result = engine.compute_component_similarity(comp1, comp2)

        # Different structures and styles should have low similarity
        assert result.style_score == 0.0  # No overlap in style refs

    def test_compute_component_similarity_with_embeddings(self, engine):
        """Test similarity with semantic embeddings."""
        comp1 = create_component("Button")
        comp2 = create_component("Button2")

        # Normalized vectors
        emb1 = [0.6, 0.8, 0.0]  # length = 1.0
        emb2 = [0.6, 0.8, 0.0]  # Identical

        result = engine.compute_component_similarity(comp1, comp2, emb1, emb2)

        assert result.semantic_score == pytest.approx(1.0, rel=0.01)

    def test_compute_component_similarity_different_embeddings(self, engine):
        """Test similarity with different embeddings."""
        comp1 = create_component("Button")
        comp2 = create_component("Card")

        emb1 = [1.0, 0.0, 0.0]
        emb2 = [0.0, 1.0, 0.0]  # Orthogonal

        result = engine.compute_component_similarity(comp1, comp2, emb1, emb2)

        assert result.semantic_score == pytest.approx(0.0, abs=0.01)

    def test_compute_style_similarity_exact_match(self, engine):
        """Test style similarity for exact hash match."""
        # Use valid hex hashes
        exact = "abc123def456abc123def456abc12345"
        near = "abc123def456abc123def456abc12345"
        style1 = create_style("a.css", exact, near)
        style2 = create_style("b.css", exact, near)

        result = engine.compute_style_similarity(style1, style2)

        assert result.structural_score == 1.0
        assert result.style_score == 1.0
        assert result.combined_score == 1.0
        assert result.classification == SimilarityClassification.DUPLICATE

    def test_compute_style_similarity_different(self, engine):
        """Test style similarity for different styles."""
        style1 = create_style(
            "a.css",
            "abc123def456abc123def456abc12345",
            "abc123def456abc123def456abc12345",
        )
        style2 = create_style(
            "b.css",
            "123456789abcdef0123456789abcdef0",
            "123456789abcdef0123456789abcdef0",
        )

        result = engine.compute_style_similarity(style1, style2)

        assert result.structural_score == 0.0  # Different exact hashes

    def test_find_similar_components(self, engine):
        """Test finding similar components."""
        same_hash = "abc123def456abc123def456abc12345"
        diff_hash = "123456789abcdef0123456789abcdef0"
        target = create_component(
            "Button", structure_hash=same_hash, style_refs=["btn", "primary"]
        )
        candidates = [
            create_component(
                "Button2", structure_hash=same_hash, style_refs=["btn", "primary"]
            ),
            create_component("Card", structure_hash=diff_hash, style_refs=["card"]),
            create_component("Button3", structure_hash=same_hash, style_refs=["btn"]),
        ]

        results = engine.find_similar_components(target, candidates, min_score=0.3)

        # Should find similar components
        assert len(results) >= 1
        # Results should be sorted by score descending
        assert all(
            results[i].combined_score >= results[i + 1].combined_score
            for i in range(len(results) - 1)
        )

    def test_find_similar_components_empty(self, engine):
        """Test with empty candidates."""
        target = create_component("Button")

        results = engine.find_similar_components(target, [])

        assert len(results) == 0

    def test_find_similar_styles(self, engine):
        """Test finding similar styles."""
        same_hash = "abc123def456abc123def456abc12345"
        diff_hash = "123456789abcdef0123456789abcdef0"
        target = create_style("a.css", same_hash, same_hash)
        candidates = [
            create_style("b.css", same_hash, same_hash),  # Exact duplicate
            create_style("c.css", diff_hash, diff_hash),
        ]

        results = engine.find_similar_styles(target, candidates)

        # Should find the exact duplicate
        assert len(results) >= 1
        assert results[0].classification == SimilarityClassification.DUPLICATE

    def test_classification_duplicate(self, engine):
        """Test classification as duplicate."""
        result = engine._classify(0.96)
        assert result == SimilarityClassification.DUPLICATE

    def test_classification_near_duplicate(self, engine):
        """Test classification as near_duplicate."""
        result = engine._classify(0.85)
        assert result == SimilarityClassification.NEAR_DUPLICATE

    def test_classification_similar(self, engine):
        """Test classification as similar."""
        result = engine._classify(0.65)
        assert result == SimilarityClassification.SIMILAR

    def test_classification_distinct(self, engine):
        """Test classification as distinct."""
        result = engine._classify(0.30)
        assert result == SimilarityClassification.DISTINCT

    def test_cosine_similarity_identical(self, engine):
        """Test cosine similarity for identical vectors."""
        vec = [0.5, 0.5, 0.5, 0.5]
        similarity = engine._cosine_similarity(vec, vec)
        assert similarity == pytest.approx(1.0, rel=0.01)

    def test_cosine_similarity_orthogonal(self, engine):
        """Test cosine similarity for orthogonal vectors."""
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        similarity = engine._cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(0.0, abs=0.01)

    def test_cosine_similarity_empty(self, engine):
        """Test cosine similarity with empty vectors."""
        assert engine._cosine_similarity([], []) == 0.0
        assert engine._cosine_similarity([1.0], []) == 0.0

    def test_cosine_similarity_mismatched_length(self, engine):
        """Test cosine similarity with different length vectors."""
        vec1 = [1.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        assert engine._cosine_similarity(vec1, vec2) == 0.0

    def test_style_ref_similarity_identical(self, engine):
        """Test Jaccard similarity for identical style refs."""
        refs = ["btn", "primary", "large"]
        similarity = engine._compute_style_ref_similarity(refs, refs)
        assert similarity == 1.0

    def test_style_ref_similarity_no_overlap(self, engine):
        """Test Jaccard similarity with no overlap."""
        refs1 = ["btn", "primary"]
        refs2 = ["card", "shadow"]
        similarity = engine._compute_style_ref_similarity(refs1, refs2)
        assert similarity == 0.0

    def test_style_ref_similarity_partial_overlap(self, engine):
        """Test Jaccard similarity with partial overlap."""
        refs1 = ["btn", "primary", "large"]
        refs2 = ["btn", "primary", "small"]
        similarity = engine._compute_style_ref_similarity(refs1, refs2)
        # 2 common out of 4 unique = 0.5
        assert similarity == 0.5

    def test_style_ref_similarity_empty(self, engine):
        """Test Jaccard similarity with empty refs."""
        assert engine._compute_style_ref_similarity([], []) == 0.0
        assert engine._compute_style_ref_similarity(["btn"], []) == 0.0

    def test_combine_scores(self, engine):
        """Test score combination with default weights."""
        # Default: semantic=0.5, structural=0.3, style=0.2
        combined = engine._combine_scores(
            semantic=1.0,
            structural=1.0,
            style=1.0,
        )
        assert combined == 1.0

    def test_combine_scores_weighted(self, engine):
        """Test weighted score combination."""
        combined = engine._combine_scores(
            semantic=1.0,  # 0.5 weight
            structural=0.0,  # 0.3 weight
            style=0.0,  # 0.2 weight
        )
        assert combined == pytest.approx(0.5, rel=0.01)

    def test_max_neighbors_limit(self, engine):
        """Test that results are limited to max_neighbors."""
        engine.engine_config.max_neighbors = 2

        same_hash = "abc123def456abc123def456abc12345"
        target = create_component(
            "Target", structure_hash=same_hash, style_refs=["btn"]
        )
        candidates = [
            create_component(f"Comp{i}", structure_hash=same_hash, style_refs=["btn"])
            for i in range(5)
        ]

        results = engine.find_similar_components(target, candidates, min_score=0.0)

        assert len(results) <= 2


class TestSimilarityClassification:
    """Tests for SimilarityClassification enum."""

    def test_values(self):
        """Test enum values."""
        assert SimilarityClassification.DUPLICATE.value == "duplicate"
        assert SimilarityClassification.NEAR_DUPLICATE.value == "near_duplicate"
        assert SimilarityClassification.SIMILAR.value == "similar"
        assert SimilarityClassification.DISTINCT.value == "distinct"
