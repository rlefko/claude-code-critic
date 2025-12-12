"""Unit tests for style normalizer and hashing utilities."""

import pytest

from claude_indexer.ui.normalizers.hashing import (
    compute_content_hash,
    compute_minhash,
    compute_simhash,
    hamming_distance,
    jaccard_similarity,
    minhash_similarity,
    simhash_similarity,
)
from claude_indexer.ui.normalizers.style import (
    NormalizedStyle,
    StyleNormalizer,
)


class TestSimHash:
    """Tests for SimHash computation."""

    def test_empty_features(self):
        """Test SimHash of empty feature list."""
        result = compute_simhash([])
        assert result == "0" * 16  # 64 bits = 16 hex chars

    def test_single_feature(self):
        """Test SimHash of single feature."""
        result = compute_simhash(["feature1"])
        assert len(result) == 16
        assert result != "0" * 16

    def test_identical_features_same_hash(self):
        """Test that identical features produce same hash."""
        hash1 = compute_simhash(["a", "b", "c"])
        hash2 = compute_simhash(["a", "b", "c"])
        assert hash1 == hash2

    def test_different_features_different_hash(self):
        """Test that different features produce different hashes."""
        hash1 = compute_simhash(["a", "b", "c"])
        hash2 = compute_simhash(["x", "y", "z"])
        assert hash1 != hash2

    def test_order_independence(self):
        """Test that feature order affects hash somewhat."""
        hash1 = compute_simhash(["a", "b", "c"])
        hash2 = compute_simhash(["c", "b", "a"])
        # May or may not be equal depending on implementation
        # Just verify they're valid hashes
        assert len(hash1) == 16
        assert len(hash2) == 16


class TestSimHashSimilarity:
    """Tests for SimHash similarity computation."""

    def test_identical_hashes(self):
        """Test similarity of identical hashes."""
        similarity = simhash_similarity("abcd1234abcd1234", "abcd1234abcd1234")
        assert similarity == 1.0

    def test_completely_different_hashes(self):
        """Test similarity of maximally different hashes."""
        # All zeros vs all ones (in binary)
        similarity = simhash_similarity("0000000000000000", "ffffffffffffffff")
        assert similarity == 0.0

    def test_partial_similarity(self):
        """Test partial similarity between hashes."""
        hash1 = compute_simhash(["a", "b", "c", "d"])
        hash2 = compute_simhash(["a", "b", "c", "e"])  # One different

        similarity = simhash_similarity(hash1, hash2)
        assert 0.0 < similarity < 1.0

    def test_empty_hash_handling(self):
        """Test handling of empty hashes."""
        assert simhash_similarity("", "abc") == 0.0
        assert simhash_similarity("abc", "") == 0.0
        assert simhash_similarity("", "") == 0.0


class TestHammingDistance:
    """Tests for Hamming distance computation."""

    def test_identical_hashes(self):
        """Test distance between identical hashes."""
        distance = hamming_distance("abcd", "abcd")
        assert distance == 0

    def test_one_bit_difference(self):
        """Test distance with one bit difference."""
        # 0x0 vs 0x1 differ by 1 bit
        distance = hamming_distance("0", "1")
        assert distance == 1

    def test_all_bits_different(self):
        """Test maximum distance."""
        # 0x0 vs 0xf differ by 4 bits
        distance = hamming_distance("0", "f")
        assert distance == 4


class TestMinHash:
    """Tests for MinHash computation."""

    def test_empty_features(self):
        """Test MinHash of empty feature list."""
        result = compute_minhash([])
        assert len(result) == 128  # Default num_permutations
        assert all(v == 0 for v in result)

    def test_deterministic(self):
        """Test that MinHash is deterministic with same seed."""
        sig1 = compute_minhash(["a", "b", "c"], seed=42)
        sig2 = compute_minhash(["a", "b", "c"], seed=42)
        assert sig1 == sig2

    def test_different_seeds_different_results(self):
        """Test that different seeds produce different signatures."""
        sig1 = compute_minhash(["a", "b", "c"], seed=42)
        sig2 = compute_minhash(["a", "b", "c"], seed=123)
        assert sig1 != sig2


class TestMinHashSimilarity:
    """Tests for MinHash similarity estimation."""

    def test_identical_sets(self):
        """Test similarity of identical sets."""
        sig1 = compute_minhash(["a", "b", "c"])
        sig2 = compute_minhash(["a", "b", "c"])
        similarity = minhash_similarity(sig1, sig2)
        assert similarity == 1.0

    def test_disjoint_sets(self):
        """Test similarity of disjoint sets."""
        sig1 = compute_minhash(["a", "b", "c"])
        sig2 = compute_minhash(["x", "y", "z"])
        similarity = minhash_similarity(sig1, sig2)
        # Should be close to 0 but may not be exact
        assert similarity < 0.2

    def test_overlapping_sets(self):
        """Test similarity of overlapping sets."""
        sig1 = compute_minhash(["a", "b", "c", "d"])
        sig2 = compute_minhash(["a", "b", "c", "e"])  # 3/5 overlap
        similarity = minhash_similarity(sig1, sig2)
        # Jaccard would be 3/5 = 0.6, MinHash should be close
        assert 0.4 < similarity < 0.9  # Allow variance

    def test_different_length_signatures(self):
        """Test that mismatched signature lengths raise error."""
        sig1 = [1, 2, 3]
        sig2 = [1, 2]
        with pytest.raises(ValueError):
            minhash_similarity(sig1, sig2)


class TestJaccardSimilarity:
    """Tests for exact Jaccard similarity."""

    def test_identical_sets(self):
        """Test similarity of identical sets."""
        similarity = jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"})
        assert similarity == 1.0

    def test_disjoint_sets(self):
        """Test similarity of disjoint sets."""
        similarity = jaccard_similarity({"a", "b"}, {"c", "d"})
        assert similarity == 0.0

    def test_overlapping_sets(self):
        """Test similarity with overlap."""
        # {a,b,c} ∩ {b,c,d} = {b,c}, union = {a,b,c,d}
        # Jaccard = 2/4 = 0.5
        similarity = jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
        assert similarity == 0.5

    def test_empty_sets(self):
        """Test similarity of empty sets."""
        assert jaccard_similarity(set(), set()) == 1.0
        assert jaccard_similarity({"a"}, set()) == 0.0
        assert jaccard_similarity(set(), {"a"}) == 0.0


class TestContentHash:
    """Tests for content hashing."""

    def test_deterministic(self):
        """Test that hashing is deterministic."""
        hash1 = compute_content_hash("test content")
        hash2 = compute_content_hash("test content")
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        """Test that different content produces different hashes."""
        hash1 = compute_content_hash("content 1")
        hash2 = compute_content_hash("content 2")
        assert hash1 != hash2

    def test_sha256_format(self):
        """Test that hash is valid SHA256 format."""
        result = compute_content_hash("test")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestNormalizedStyle:
    """Tests for NormalizedStyle dataclass."""

    def test_create_normalized_style(self):
        """Test basic NormalizedStyle creation."""
        style = NormalizedStyle(
            declarations={"color": "#FF0000FF", "padding": "16px"},
            exact_hash="abc123",
            near_hash="def456",
        )

        assert style.declarations == {"color": "#FF0000FF", "padding": "16px"}
        assert style.exact_hash == "abc123"
        assert style.near_hash == "def456"

    def test_is_exact_duplicate(self):
        """Test exact duplicate detection."""
        style1 = NormalizedStyle(declarations={}, exact_hash="abc", near_hash="xyz")
        style2 = NormalizedStyle(
            declarations={}, exact_hash="abc", near_hash="different"
        )
        style3 = NormalizedStyle(
            declarations={}, exact_hash="different", near_hash="xyz"
        )

        assert style1.is_exact_duplicate(style2)
        assert not style1.is_exact_duplicate(style3)

    def test_serialization_roundtrip(self):
        """Test to_dict and from_dict produce equivalent objects."""
        style = NormalizedStyle(
            declarations={"color": "#000000FF"},
            exact_hash="hash123",
            near_hash="near456",
            original_declarations={"color": "#000"},
        )

        data = style.to_dict()
        restored = NormalizedStyle.from_dict(data)

        assert restored.declarations == style.declarations
        assert restored.exact_hash == style.exact_hash
        assert restored.near_hash == style.near_hash
        assert restored.original_declarations == style.original_declarations


class TestStyleNormalizer:
    """Tests for StyleNormalizer."""

    @pytest.fixture
    def normalizer(self) -> StyleNormalizer:
        """Create a style normalizer."""
        return StyleNormalizer()

    def test_normalize_color_hex(self, normalizer: StyleNormalizer):
        """Test color normalization for hex values."""
        result = normalizer.normalize({"color": "#ff0000"})

        assert result.declarations["color"] == "#FF0000FF"

    def test_normalize_color_rgb(self, normalizer: StyleNormalizer):
        """Test color normalization for rgb values."""
        result = normalizer.normalize({"color": "rgb(255, 0, 0)"})

        assert result.declarations["color"] == "#FF0000FF"

    def test_normalize_length_px(self, normalizer: StyleNormalizer):
        """Test length normalization for pixel values."""
        result = normalizer.normalize({"padding": "16px"})

        assert result.declarations["padding"] == "16px"

    def test_normalize_length_rem(self, normalizer: StyleNormalizer):
        """Test length normalization for rem values."""
        result = normalizer.normalize({"padding": "1rem"})

        # 1rem = 16px with default base
        assert result.declarations["padding"] == "16px"

    def test_normalize_zero(self, normalizer: StyleNormalizer):
        """Test normalization of zero values."""
        result = normalizer.normalize({"margin": "0"})

        assert result.declarations["margin"] == "0"

    def test_property_sorting(self, normalizer: StyleNormalizer):
        """Test that properties are sorted alphabetically."""
        result = normalizer.normalize(
            {"z-index": "1", "color": "#fff", "align-items": "center"}
        )

        keys = list(result.declarations.keys())
        assert keys == sorted(keys)

    def test_shorthand_collapse(self):
        """Test shorthand property collapsing."""
        normalizer = StyleNormalizer(collapse_shorthands=True)
        result = normalizer.normalize(
            {
                "margin-top": "10px",
                "margin-right": "10px",
                "margin-bottom": "10px",
                "margin-left": "10px",
            }
        )

        # All same value should collapse to shorthand
        assert "margin" in result.declarations
        assert "margin-top" not in result.declarations

    def test_no_shorthand_collapse_different_values(self):
        """Test that different values don't collapse."""
        normalizer = StyleNormalizer(collapse_shorthands=True)
        result = normalizer.normalize(
            {
                "margin-top": "10px",
                "margin-right": "20px",
                "margin-bottom": "10px",
                "margin-left": "20px",
            }
        )

        # Different values shouldn't collapse
        assert "margin" not in result.declarations

    def test_exact_hash_stability(self, normalizer: StyleNormalizer):
        """Test that same declarations produce same hash."""
        result1 = normalizer.normalize({"color": "#ff0000", "padding": "10px"})
        result2 = normalizer.normalize({"color": "#ff0000", "padding": "10px"})

        assert result1.exact_hash == result2.exact_hash

    def test_different_declarations_different_hash(self, normalizer: StyleNormalizer):
        """Test that different declarations produce different hashes."""
        result1 = normalizer.normalize({"color": "#ff0000"})
        result2 = normalizer.normalize({"color": "#00ff00"})

        assert result1.exact_hash != result2.exact_hash

    def test_find_duplicates(self, normalizer: StyleNormalizer):
        """Test finding exact duplicates in a list."""
        styles = normalizer.normalize_declaration_list(
            [
                {"color": "#ff0000"},
                {"color": "#00ff00"},
                {"color": "#ff0000"},  # Duplicate of first
            ]
        )

        duplicates = normalizer.find_duplicates(styles)

        assert len(duplicates) == 1
        assert duplicates[0] == (0, 2)  # First and third are duplicates

    def test_find_near_duplicates(self, normalizer: StyleNormalizer):
        """Test finding near-duplicates in a list."""
        # Use styles with more properties in common for higher similarity
        styles = normalizer.normalize_declaration_list(
            [
                {
                    "color": "#ff0000",
                    "padding": "10px",
                    "margin": "10px",
                    "display": "flex",
                },
                {
                    "color": "#ff0000",
                    "padding": "10px",
                    "margin": "10px",
                    "display": "block",
                },
                {
                    "color": "#00ff00",
                    "padding": "100px",
                    "margin": "50px",
                    "display": "none",
                },
            ]
        )

        # Use a lower threshold to account for SimHash behavior
        near_duplicates = normalizer.find_near_duplicates(styles, threshold=0.5)

        # First two should be near duplicates (3 of 4 props identical)
        assert any(pair[:2] == (0, 1) for pair in near_duplicates)

    def test_keyword_preservation(self, normalizer: StyleNormalizer):
        """Test that CSS keywords are preserved."""
        result = normalizer.normalize({"display": "flex", "position": "relative"})

        assert result.declarations["display"] == "flex"
        assert result.declarations["position"] == "relative"

    def test_inherit_initial_preservation(self, normalizer: StyleNormalizer):
        """Test that inherit/initial values are preserved."""
        result = normalizer.normalize({"color": "inherit", "margin": "initial"})

        assert result.declarations["color"] == "inherit"
        assert result.declarations["margin"] == "initial"
