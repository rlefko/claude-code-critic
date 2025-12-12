"""Tests for the QueryResultCache."""

import time
from unittest.mock import patch

import pytest

from claude_indexer.storage.query_cache import CacheEntry, QueryResultCache


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_basic_creation(self):
        """Test basic CacheEntry creation."""
        entry = CacheEntry(
            result={"data": "test"},
            created_at=time.time(),
        )

        assert entry.result == {"data": "test"}
        assert entry.access_count == 0

    def test_access_count_increment(self):
        """Test access count tracking."""
        entry = CacheEntry(
            result="test",
            created_at=time.time(),
        )

        entry.access_count += 1
        assert entry.access_count == 1


class TestQueryResultCache:
    """Tests for QueryResultCache."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache instance."""
        return QueryResultCache(max_entries=100, ttl_seconds=60.0)

    def test_basic_set_and_get(self, cache):
        """Test basic cache set and get."""
        query_vector = [0.1] * 10
        result = {"items": [1, 2, 3]}

        cache.set("collection1", query_vector, 10, None, "semantic", result)
        cached = cache.get("collection1", query_vector, 10, None, "semantic")

        assert cached == result

    def test_cache_miss(self, cache):
        """Test cache miss returns None."""
        result = cache.get("nonexistent", [0.1] * 10, 10, None, "semantic")
        assert result is None

    def test_different_collections(self, cache):
        """Test cache isolation between collections."""
        vector = [0.1] * 10
        result1 = {"collection": "1"}
        result2 = {"collection": "2"}

        cache.set("collection1", vector, 10, None, "semantic", result1)
        cache.set("collection2", vector, 10, None, "semantic", result2)

        assert cache.get("collection1", vector, 10, None, "semantic") == result1
        assert cache.get("collection2", vector, 10, None, "semantic") == result2

    def test_different_limits(self, cache):
        """Test cache keys differ by limit."""
        vector = [0.1] * 10
        result10 = {"limit": 10}
        result20 = {"limit": 20}

        cache.set("collection", vector, 10, None, "semantic", result10)
        cache.set("collection", vector, 20, None, "semantic", result20)

        assert cache.get("collection", vector, 10, None, "semantic") == result10
        assert cache.get("collection", vector, 20, None, "semantic") == result20

    def test_different_filters(self, cache):
        """Test cache keys differ by filters."""
        vector = [0.1] * 10
        result_no_filter = {"filter": None}
        result_with_filter = {"filter": "active"}

        cache.set("collection", vector, 10, None, "semantic", result_no_filter)
        cache.set("collection", vector, 10, {"status": "active"}, "semantic", result_with_filter)

        assert cache.get("collection", vector, 10, None, "semantic") == result_no_filter
        assert cache.get("collection", vector, 10, {"status": "active"}, "semantic") == result_with_filter

    def test_different_search_modes(self, cache):
        """Test cache keys differ by search mode."""
        vector = [0.1] * 10
        result_semantic = {"mode": "semantic"}
        result_hybrid = {"mode": "hybrid"}

        cache.set("collection", vector, 10, None, "semantic", result_semantic)
        cache.set("collection", vector, 10, None, "hybrid", result_hybrid)

        assert cache.get("collection", vector, 10, None, "semantic") == result_semantic
        assert cache.get("collection", vector, 10, None, "hybrid") == result_hybrid

    def test_ttl_expiration(self, cache):
        """Test TTL expiration."""
        cache = QueryResultCache(max_entries=100, ttl_seconds=0.1)  # 100ms TTL

        vector = [0.1] * 10
        cache.set("collection", vector, 10, None, "semantic", "result")

        # Should be cached initially
        assert cache.get("collection", vector, 10, None, "semantic") == "result"

        # Wait for TTL to expire
        time.sleep(0.15)

        # Should be expired
        assert cache.get("collection", vector, 10, None, "semantic") is None

    def test_lru_eviction(self):
        """Test LRU eviction when max entries reached."""
        cache = QueryResultCache(max_entries=3, ttl_seconds=60.0)

        for i in range(5):
            cache.set(f"coll{i}", [float(i)] * 10, 10, None, "semantic", f"result{i}")

        # Only last 3 should remain
        assert cache.get("coll0", [0.0] * 10, 10, None, "semantic") is None
        assert cache.get("coll1", [1.0] * 10, 10, None, "semantic") is None
        assert cache.get("coll2", [2.0] * 10, 10, None, "semantic") == "result2"
        assert cache.get("coll3", [3.0] * 10, 10, None, "semantic") == "result3"
        assert cache.get("coll4", [4.0] * 10, 10, None, "semantic") == "result4"

    def test_invalidate_collection(self, cache):
        """Test invalidating specific collection."""
        cache.set("coll1", [0.1] * 10, 10, None, "semantic", "result1")
        cache.set("coll2", [0.1] * 10, 10, None, "semantic", "result2")

        count = cache.invalidate("coll1")
        assert count == 1

        # coll1 should be gone
        assert cache.get("coll1", [0.1] * 10, 10, None, "semantic") is None
        # coll2 should remain
        assert cache.get("coll2", [0.1] * 10, 10, None, "semantic") == "result2"

    def test_invalidate_all(self, cache):
        """Test invalidating all entries."""
        cache.set("coll1", [0.1] * 10, 10, None, "semantic", "result1")
        cache.set("coll2", [0.1] * 10, 10, None, "semantic", "result2")

        count = cache.invalidate()
        assert count == 2

        assert cache.get("coll1", [0.1] * 10, 10, None, "semantic") is None
        assert cache.get("coll2", [0.1] * 10, 10, None, "semantic") is None

    def test_prune_expired(self, cache):
        """Test pruning expired entries."""
        cache = QueryResultCache(max_entries=100, ttl_seconds=0.1)

        cache.set("coll1", [0.1] * 10, 10, None, "semantic", "result1")
        cache.set("coll2", [0.2] * 10, 10, None, "semantic", "result2")

        # Wait for TTL to expire
        time.sleep(0.15)

        count = cache.prune_expired()
        assert count == 2
        assert len(cache) == 0

    def test_stats(self, cache):
        """Test cache statistics."""
        vector = [0.1] * 10

        # Initial stats
        stats = cache.get_stats()
        assert stats["entries"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        # Add entry and access
        cache.set("coll", vector, 10, None, "semantic", "result")
        cache.get("coll", vector, 10, None, "semantic")  # Hit
        cache.get("nonexistent", vector, 10, None, "semantic")  # Miss

        stats = cache.get_stats()
        assert stats["entries"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_ratio"] == 0.5

    def test_clear_stats(self, cache):
        """Test clearing statistics."""
        cache.set("coll", [0.1] * 10, 10, None, "semantic", "result")
        cache.get("coll", [0.1] * 10, 10, None, "semantic")

        cache.clear_stats()

        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_len(self, cache):
        """Test __len__ method."""
        assert len(cache) == 0

        cache.set("coll1", [0.1] * 10, 10, None, "semantic", "result1")
        assert len(cache) == 1

        cache.set("coll2", [0.2] * 10, 10, None, "semantic", "result2")
        assert len(cache) == 2

    def test_thread_safety(self, cache):
        """Test thread-safe operations."""
        import threading

        results = []
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.set(f"thread_coll_{i}", [float(i)] * 10, 10, None, "semantic", f"result_{i}")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(100):
                    cache.get(f"thread_coll_{i}", [float(i)] * 10, 10, None, "semantic")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
