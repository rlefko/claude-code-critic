"""LRU cache for Qdrant query results with TTL-based expiration.

This module provides caching for vector search results to reduce
latency for repeated or similar queries. The cache uses content-hash
based keys and supports automatic TTL-based expiration.

Example usage:
    cache = QueryResultCache(max_entries=1000, ttl_seconds=60.0)

    # Check cache before search
    cached = cache.get(collection, vector, limit, filters, mode)
    if cached is not None:
        return cached

    # Perform search
    results = qdrant_search(...)

    # Store in cache
    cache.set(collection, vector, limit, filters, mode, results)

    # Invalidate on write
    cache.invalidate(collection_name)
"""

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass
class CacheEntry:
    """Cached query result with metadata.

    Attributes:
        result: The cached search result.
        created_at: Timestamp when entry was created.
        access_count: Number of times this entry has been accessed.
    """

    result: Any
    created_at: float
    access_count: int = 0


class QueryResultCache:
    """LRU cache for vector search results with TTL expiration.

    Provides caching for Qdrant search operations to reduce latency
    for repeated queries. Features include:

    - Content-hash based keys from query parameters
    - TTL-based expiration (default: 60 seconds)
    - LRU eviction when max entries reached
    - Thread-safe operations
    - Collection-level invalidation for incremental indexing

    Attributes:
        max_entries: Maximum number of cache entries.
        ttl_seconds: Time-to-live for cache entries in seconds.

    Example:
        cache = QueryResultCache(max_entries=1000, ttl_seconds=60.0)

        # Cache lookup
        cached = cache.get("my_collection", query_vec, 10, None, "semantic")
        if cached:
            return cached

        # Cache store
        results = perform_search(...)
        cache.set("my_collection", query_vec, 10, None, "semantic", results)

        # Invalidate on collection modification
        cache.invalidate("my_collection")
    """

    def __init__(
        self,
        max_entries: int = 1000,
        ttl_seconds: float = 60.0,
    ):
        """Initialize the query result cache.

        Args:
            max_entries: Maximum number of entries to cache.
            ttl_seconds: Time-to-live for cache entries.
        """
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._collection_keys: dict[str, set[str]] = {}  # collection -> set of cache keys
        self._lock = Lock()

        # Statistics
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _compute_key(
        collection_name: str,
        query_vector: list[float] | None,
        limit: int,
        filter_conditions: dict[str, Any] | None,
        search_mode: str = "semantic",
    ) -> str:
        """Compute cache key from query parameters.

        Creates a deterministic hash from the query parameters that
        uniquely identifies the search operation.

        Args:
            collection_name: Name of the Qdrant collection.
            query_vector: The query embedding vector (or None for BM25).
            limit: Maximum number of results.
            filter_conditions: Optional filter conditions.
            search_mode: Search mode (semantic, keyword, hybrid).

        Returns:
            A 16-character hex string cache key.
        """
        # Use first 10 elements of vector for key (balance uniqueness vs speed)
        vector_sig = None
        if query_vector:
            # Round to reduce floating point variations
            rounded = [round(v, 6) for v in query_vector[:10]]
            vector_sig = hashlib.md5(json.dumps(rounded).encode()).hexdigest()[:8]

        key_data = {
            "c": collection_name,
            "v": vector_sig,
            "l": limit,
            "f": json.dumps(filter_conditions, sort_keys=True) if filter_conditions else None,
            "m": search_mode,
        }
        return hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()[:16]

    def get(
        self,
        collection_name: str,
        query_vector: list[float] | None,
        limit: int,
        filter_conditions: dict[str, Any] | None = None,
        search_mode: str = "semantic",
    ) -> Any | None:
        """Get cached result if valid.

        Checks the cache for a matching entry. Returns None if:
        - No matching entry exists
        - The entry has expired (exceeded TTL)

        On hit, the entry is moved to the end (LRU) and access count incremented.

        Args:
            collection_name: Name of the Qdrant collection.
            query_vector: The query embedding vector.
            limit: Maximum number of results.
            filter_conditions: Optional filter conditions.
            search_mode: Search mode (semantic, keyword, hybrid).

        Returns:
            Cached result or None if not found/expired.
        """
        key = self._compute_key(collection_name, query_vector, limit, filter_conditions, search_mode)

        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            # Check TTL
            if time.time() - entry.created_at > self.ttl_seconds:
                self._remove_key(key, collection_name)
                self._misses += 1
                return None

            # Move to end (LRU) and increment access count
            self._cache.move_to_end(key)
            entry.access_count += 1
            self._hits += 1
            return entry.result

    def set(
        self,
        collection_name: str,
        query_vector: list[float] | None,
        limit: int,
        filter_conditions: dict[str, Any] | None,
        search_mode: str,
        result: Any,
    ) -> None:
        """Store result in cache.

        Adds or updates a cache entry. If the cache is at capacity,
        evicts the least recently used entry.

        Args:
            collection_name: Name of the Qdrant collection.
            query_vector: The query embedding vector.
            limit: Maximum number of results.
            filter_conditions: Optional filter conditions.
            search_mode: Search mode (semantic, keyword, hybrid).
            result: The search result to cache.
        """
        key = self._compute_key(collection_name, query_vector, limit, filter_conditions, search_mode)

        with self._lock:
            # Evict oldest if at capacity
            while len(self._cache) >= self.max_entries:
                oldest_key, _ = self._cache.popitem(last=False)
                # Remove from collection index
                for coll_keys in self._collection_keys.values():
                    coll_keys.discard(oldest_key)

            # Add entry
            self._cache[key] = CacheEntry(
                result=result,
                created_at=time.time(),
            )

            # Track by collection for efficient invalidation
            if collection_name not in self._collection_keys:
                self._collection_keys[collection_name] = set()
            self._collection_keys[collection_name].add(key)

    def _remove_key(self, key: str, collection_name: str) -> None:
        """Remove a key from cache and collection index.

        Internal method - caller must hold lock.

        Args:
            key: Cache key to remove.
            collection_name: Collection the key belongs to.
        """
        if key in self._cache:
            del self._cache[key]
        if collection_name in self._collection_keys:
            self._collection_keys[collection_name].discard(key)

    def invalidate(self, collection_name: str | None = None) -> int:
        """Invalidate cache entries.

        Removes cache entries for a specific collection or all entries.
        Called when collection data is modified (indexing, delete, etc).

        Args:
            collection_name: If provided, only invalidate entries for this
                           collection. If None, clear all entries.

        Returns:
            Number of entries invalidated.
        """
        with self._lock:
            if collection_name is None:
                count = len(self._cache)
                self._cache.clear()
                self._collection_keys.clear()
                return count

            # Invalidate by collection
            if collection_name not in self._collection_keys:
                return 0

            keys_to_remove = self._collection_keys[collection_name].copy()
            for key in keys_to_remove:
                if key in self._cache:
                    del self._cache[key]

            del self._collection_keys[collection_name]
            return len(keys_to_remove)

    def prune_expired(self) -> int:
        """Remove all expired entries.

        Scans the cache and removes entries that have exceeded TTL.
        This is called automatically on get(), but can be called
        manually for maintenance.

        Returns:
            Number of entries pruned.
        """
        with self._lock:
            now = time.time()
            expired_keys: list[tuple[str, str]] = []

            for key, entry in self._cache.items():
                if now - entry.created_at > self.ttl_seconds:
                    # Find collection for this key
                    for coll, keys in self._collection_keys.items():
                        if key in keys:
                            expired_keys.append((key, coll))
                            break
                    else:
                        # Key not in any collection index (shouldn't happen)
                        expired_keys.append((key, ""))

            for key, collection in expired_keys:
                if key in self._cache:
                    del self._cache[key]
                if collection and collection in self._collection_keys:
                    self._collection_keys[collection].discard(key)

            return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache performance metrics:
            - entries: Current number of entries
            - max_entries: Maximum capacity
            - ttl_seconds: TTL configuration
            - hits: Number of cache hits
            - misses: Number of cache misses
            - hit_ratio: Ratio of hits to total requests
            - collections: Number of collections cached
        """
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._cache),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": self._hits / total if total > 0 else 0.0,
                "collections": len(self._collection_keys),
            }

    def clear_stats(self) -> None:
        """Reset hit/miss statistics."""
        with self._lock:
            self._hits = 0
            self._misses = 0

    def __len__(self) -> int:
        """Return number of entries in cache."""
        with self._lock:
            return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in cache (does not update LRU)."""
        with self._lock:
            return key in self._cache


__all__ = ["QueryResultCache", "CacheEntry"]
