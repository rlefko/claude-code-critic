"""Unit tests for CI fingerprint caching."""

import tempfile
from pathlib import Path

import pytest

from claude_indexer.ui.ci.cache import (
    CacheEntry,
    CacheManager,
    CacheMetadata,
    FingerprintCache,
)
from claude_indexer.ui.config import UIQualityConfig
from claude_indexer.ui.models import (
    StaticComponentFingerprint,
    StyleFingerprint,
)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_create_cache_entry(self):
        """Test basic CacheEntry creation."""
        entry = CacheEntry(
            file_path="/src/Button.tsx",
            content_hash="abc123",
            style_fingerprints=[{"exact_hash": "hash1"}],
            component_fingerprints=[{"structure_hash": "hash2"}],
        )

        assert entry.file_path == "/src/Button.tsx"
        assert entry.content_hash == "abc123"
        assert len(entry.style_fingerprints) == 1
        assert len(entry.component_fingerprints) == 1

    def test_cache_entry_to_dict(self):
        """Test CacheEntry serialization."""
        entry = CacheEntry(
            file_path="/src/Button.tsx",
            content_hash="abc123",
            style_fingerprints=[{"exact_hash": "hash1"}],
        )

        data = entry.to_dict()

        assert data["file_path"] == "/src/Button.tsx"
        assert data["content_hash"] == "abc123"
        assert len(data["style_fingerprints"]) == 1
        assert "extracted_at" in data

    def test_cache_entry_from_dict(self):
        """Test CacheEntry deserialization."""
        data = {
            "file_path": "/src/Card.tsx",
            "content_hash": "def456",
            "style_fingerprints": [{"exact_hash": "h1"}],
            "component_fingerprints": [],
            "extracted_at": "2024-01-01T00:00:00",
        }

        entry = CacheEntry.from_dict(data)

        assert entry.file_path == "/src/Card.tsx"
        assert entry.content_hash == "def456"
        assert entry.extracted_at == "2024-01-01T00:00:00"


class TestCacheMetadata:
    """Tests for CacheMetadata dataclass."""

    def test_create_cache_metadata(self):
        """Test basic CacheMetadata creation."""
        metadata = CacheMetadata(
            project_path="/project",
            config_hash="config123",
            total_entries=10,
        )

        assert metadata.project_path == "/project"
        assert metadata.config_hash == "config123"
        assert metadata.total_entries == 10
        assert metadata.version == "1.0"

    def test_cache_metadata_round_trip(self):
        """Test CacheMetadata serialization round-trip."""
        metadata = CacheMetadata(
            project_path="/project",
            config_hash="hash123",
            total_entries=5,
        )

        data = metadata.to_dict()
        restored = CacheMetadata.from_dict(data)

        assert restored.project_path == "/project"
        assert restored.config_hash == "hash123"
        assert restored.total_entries == 5


class TestFingerprintCache:
    """Tests for FingerprintCache class."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def config(self):
        """Create a test UI quality config."""
        return UIQualityConfig()

    @pytest.fixture
    def cache(self, temp_project, config):
        """Create a FingerprintCache instance."""
        return FingerprintCache(temp_project, config)

    def test_cache_set_and_get(self, cache, temp_project):
        """Test setting and getting cache entries."""
        # Create a test file
        test_file = temp_project / "test.tsx"
        test_file.write_text("content")

        # Create fingerprints
        style_fp = StyleFingerprint(
            declaration_set={"color": "#333"},
            exact_hash="abc123",
            near_hash="def456",
        )
        component_fp = StaticComponentFingerprint(
            structure_hash="struct123",
            style_refs=["btn"],
        )

        # Set cache
        cache.set(test_file, "content_hash_123", [style_fp], [component_fp])

        # Get cache
        entry = cache.get(test_file, "content_hash_123")

        assert entry is not None
        assert entry.content_hash == "content_hash_123"
        assert len(entry.style_fingerprints) == 1
        assert len(entry.component_fingerprints) == 1

    def test_cache_miss_no_entry(self, cache, temp_project):
        """Test cache miss when no entry exists."""
        test_file = temp_project / "test.tsx"
        test_file.write_text("content")

        entry = cache.get(test_file, "any_hash")

        assert entry is None

    def test_cache_miss_wrong_hash(self, cache, temp_project):
        """Test cache miss when content hash changed."""
        test_file = temp_project / "test.tsx"
        test_file.write_text("content")

        # Set with one hash
        style_fp = StyleFingerprint(
            declaration_set={},
            exact_hash="abc",
            near_hash="def",
        )
        cache.set(test_file, "old_hash", [style_fp], [])

        # Get with different hash
        entry = cache.get(test_file, "new_hash")

        assert entry is None

    def test_cache_invalidate(self, cache, temp_project):
        """Test invalidating a cache entry."""
        test_file = temp_project / "test.tsx"
        test_file.write_text("content")

        # Set cache
        style_fp = StyleFingerprint(
            declaration_set={},
            exact_hash="abc",
            near_hash="def",
        )
        cache.set(test_file, "hash123", [style_fp], [])

        # Invalidate
        cache.invalidate(test_file)

        # Should miss now
        entry = cache.get(test_file, "hash123")
        assert entry is None

    def test_cache_clear(self, cache, temp_project):
        """Test clearing entire cache."""
        test_file = temp_project / "test.tsx"
        test_file.write_text("content")

        # Add entry
        style_fp = StyleFingerprint(
            declaration_set={},
            exact_hash="abc",
            near_hash="def",
        )
        cache.set(test_file, "hash123", [style_fp], [])

        assert cache.size == 1

        # Clear
        cache.clear()

        assert cache.size == 0

    def test_cache_persistence(self, temp_project, config):
        """Test saving and loading cache from disk."""
        # Create and populate cache
        cache1 = FingerprintCache(temp_project, config)

        test_file = temp_project / "test.tsx"
        test_file.write_text("content")

        style_fp = StyleFingerprint(
            declaration_set={"color": "#333"},
            exact_hash="abc123",
            near_hash="def456",
        )
        cache1.set(test_file, "content_hash", [style_fp], [])
        cache1.save()

        # Create new cache and load
        cache2 = FingerprintCache(temp_project, config)
        loaded = cache2.load()

        assert loaded is True
        assert cache2.size == 1

        entry = cache2.get(test_file, "content_hash")
        assert entry is not None

    def test_cache_config_invalidation(self, temp_project):
        """Test cache invalidation when config changes."""
        # Create config and populate cache
        config1 = UIQualityConfig()
        cache1 = FingerprintCache(temp_project, config1)

        test_file = temp_project / "test.tsx"
        test_file.write_text("content")

        style_fp = StyleFingerprint(
            declaration_set={},
            exact_hash="abc",
            near_hash="def",
        )
        cache1.set(test_file, "hash123", [style_fp], [])
        cache1.save()

        # Create new config with different thresholds
        config2 = UIQualityConfig()
        config2.gating.similarity_thresholds.duplicate = 0.99  # Changed
        cache2 = FingerprintCache(temp_project, config2)
        loaded = cache2.load()

        # Should not load due to config change
        assert loaded is False
        assert cache2.size == 0


class TestCacheManager:
    """Tests for CacheManager class."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def config(self):
        """Create a test UI quality config."""
        return UIQualityConfig()

    @pytest.fixture
    def manager(self, temp_project, config):
        """Create a CacheManager instance."""
        return CacheManager(temp_project, config)

    def test_content_hash(self, manager, temp_project):
        """Test computing content hash."""
        test_file = temp_project / "test.txt"
        test_file.write_text("hello world")

        hash1 = manager.get_content_hash(test_file)

        assert hash1 != ""
        assert len(hash1) == 64  # SHA256 hex length

        # Same content should give same hash
        hash2 = manager.get_content_hash(test_file)
        assert hash1 == hash2

        # Different content should give different hash
        test_file.write_text("different content")
        hash3 = manager.get_content_hash(test_file)
        assert hash1 != hash3

    def test_cache_fingerprints(self, manager, temp_project):
        """Test caching and retrieving fingerprints."""
        test_file = temp_project / "test.tsx"
        test_file.write_text("component code")

        style_fp = StyleFingerprint(
            declaration_set={"padding": "8px"},
            exact_hash="style_hash",
            near_hash="near_hash",
        )
        component_fp = StaticComponentFingerprint(
            structure_hash="struct_hash",
            style_refs=["btn-primary"],
        )

        # Cache fingerprints
        manager.cache_fingerprints(test_file, [style_fp], [component_fp])

        # Retrieve
        result = manager.get_cached_fingerprints(test_file)

        assert result is not None
        styles, components = result
        assert len(styles) == 1
        assert len(components) == 1
        assert styles[0].exact_hash == "style_hash"
        assert components[0].structure_hash == "struct_hash"

    def test_cache_hit_rate(self, manager, temp_project):
        """Test cache hit rate tracking."""
        test_file = temp_project / "test.tsx"
        test_file.write_text("content")

        # Initial state
        assert manager.hit_rate == 0.0

        # Cache miss
        manager.get_cached_fingerprints(test_file)
        assert manager._misses == 1

        # Cache entry
        style_fp = StyleFingerprint(
            declaration_set={},
            exact_hash="abc",
            near_hash="def",
        )
        manager.cache_fingerprints(test_file, [style_fp], [])

        # Cache hit
        manager.get_cached_fingerprints(test_file)
        assert manager._hits == 1

        # Hit rate should be 50%
        assert manager.hit_rate == 0.5

    def test_cache_stats(self, manager, temp_project):
        """Test cache statistics."""
        test_file = temp_project / "test.tsx"
        test_file.write_text("content")

        # Generate some stats
        manager.get_cached_fingerprints(test_file)  # miss
        style_fp = StyleFingerprint(
            declaration_set={},
            exact_hash="abc",
            near_hash="def",
        )
        manager.cache_fingerprints(test_file, [style_fp], [])
        manager.get_cached_fingerprints(test_file)  # hit

        stats = manager.stats

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["size"] == 1

    def test_initialize_and_finalize(self, manager, temp_project):
        """Test initialize and finalize lifecycle."""
        test_file = temp_project / "test.tsx"
        test_file.write_text("content")

        # Initialize (loads cache)
        manager.initialize()

        # Cache something
        style_fp = StyleFingerprint(
            declaration_set={},
            exact_hash="abc",
            near_hash="def",
        )
        manager.cache_fingerprints(test_file, [style_fp], [])

        # Finalize (saves cache)
        manager.finalize()

        # Create new manager and verify persistence
        manager2 = CacheManager(temp_project, manager.config)
        manager2.initialize()

        result = manager2.get_cached_fingerprints(test_file)
        assert result is not None
