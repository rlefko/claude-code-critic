#!/usr/bin/env python3
"""
Guard Cache - LRU cache for embeddings and analysis results.

Provides caching layer for Memory Guard to improve performance:
- Embedding cache: Avoids re-computing embeddings for same code
- Analysis cache: Stores Tier 3 results with TTL for repeated edits
- Content hash based lookup for efficient cache hits
"""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class CacheEntry:
    """A cached entry with TTL."""

    value: Any
    created_at: float
    ttl_seconds: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        return (time.time() - self.created_at) > self.ttl_seconds

    def touch(self) -> None:
        """Update access statistics."""
        self.access_count += 1
        self.last_accessed = time.time()


class LRUCache:
    """Thread-safe LRU cache with TTL support."""

    def __init__(self, max_size: int = 100, default_ttl: float = 300.0):
        """Initialize LRU cache.

        Args:
            max_size: Maximum number of entries to store
            default_ttl: Default TTL in seconds (5 minutes)
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> tuple[bool, Any]:
        """Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Tuple of (found, value). If not found or expired, returns (False, None)
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return False, None

            entry = self._cache[key]

            # Check expiration
            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return False, None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.touch()
            self._hits += 1
            return True, entry.value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Set a value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL override in seconds
        """
        with self._lock:
            # Remove if exists (to update position)
            if key in self._cache:
                del self._cache[key]

            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            # Add new entry
            self._cache[key] = CacheEntry(
                value=value,
                created_at=time.time(),
                ttl_seconds=ttl if ttl is not None else self._default_ttl,
            )

    def invalidate(self, key: str) -> bool:
        """Remove a specific key from cache.

        Args:
            key: Cache key to invalidate

        Returns:
            True if key was found and removed
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> int:
        """Clear all entries from cache.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "default_ttl": self._default_ttl,
            }


class GuardCache:
    """High-level cache manager for Memory Guard.

    Provides separate caches for:
    - Embeddings: content_hash -> embedding vector
    - Analysis results: content_hash -> Tier 3 analysis result
    """

    # Singleton instance
    _instance: Optional["GuardCache"] = None
    _lock = threading.Lock()

    def __init__(
        self,
        embedding_ttl: float = 3600.0,  # 1 hour
        analysis_ttl: float = 300.0,  # 5 minutes
        max_embeddings: int = 500,
        max_analyses: int = 100,
    ):
        """Initialize guard cache.

        Args:
            embedding_ttl: TTL for embedding cache (default 1 hour)
            analysis_ttl: TTL for analysis cache (default 5 minutes)
            max_embeddings: Max embedding entries to cache
            max_analyses: Max analysis entries to cache
        """
        self.embedding_cache = LRUCache(
            max_size=max_embeddings, default_ttl=embedding_ttl
        )
        self.analysis_cache = LRUCache(max_size=max_analyses, default_ttl=analysis_ttl)
        self._persistence_path: Path | None = None

    @classmethod
    def get_instance(cls) -> "GuardCache":
        """Get singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute hash for content-based cache lookup.

        Args:
            content: Code content to hash

        Returns:
            SHA256 hash string (first 16 chars for compactness)
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def get_cached_embedding(self, content: str) -> tuple[bool, list[float] | None]:
        """Get cached embedding for content.

        Args:
            content: Code content

        Returns:
            Tuple of (found, embedding)
        """
        content_hash = self.compute_content_hash(content)
        return self.embedding_cache.get(content_hash)

    def cache_embedding(self, content: str, embedding: list[float]) -> None:
        """Cache embedding for content.

        Args:
            content: Code content
            embedding: Embedding vector
        """
        content_hash = self.compute_content_hash(content)
        self.embedding_cache.set(content_hash, embedding)

    def get_cached_analysis(
        self, file_path: str, content: str
    ) -> tuple[bool, dict[str, Any] | None]:
        """Get cached Tier 3 analysis result.

        Args:
            file_path: File path
            content: Code content

        Returns:
            Tuple of (found, analysis_result)
        """
        # Key includes both file path and content for uniqueness
        cache_key = f"{file_path}:{self.compute_content_hash(content)}"
        return self.analysis_cache.get(cache_key)

    def cache_analysis(
        self, file_path: str, content: str, result: dict[str, Any]
    ) -> None:
        """Cache Tier 3 analysis result.

        Args:
            file_path: File path
            content: Code content
            result: Analysis result to cache
        """
        cache_key = f"{file_path}:{self.compute_content_hash(content)}"
        self.analysis_cache.set(cache_key, result)

    def invalidate_file(self, file_path: str) -> None:
        """Invalidate all cache entries for a file.

        Note: This only invalidates by exact key match.
        For comprehensive invalidation, clear the analysis cache.
        """
        # Analysis cache keys start with file_path
        # This is a best-effort approach
        with self.analysis_cache._lock:
            keys_to_remove = [
                key
                for key in self.analysis_cache._cache
                if key.startswith(f"{file_path}:")
            ]
            for key in keys_to_remove:
                del self.analysis_cache._cache[key]

    def get_stats(self) -> dict[str, Any]:
        """Get combined cache statistics."""
        return {
            "embedding_cache": self.embedding_cache.get_stats(),
            "analysis_cache": self.analysis_cache.get_stats(),
        }

    def cleanup(self) -> dict[str, int]:
        """Cleanup expired entries from all caches.

        Returns:
            Dict with cleanup counts per cache
        """
        return {
            "embeddings_cleaned": self.embedding_cache.cleanup_expired(),
            "analyses_cleaned": self.analysis_cache.cleanup_expired(),
        }

    def save_to_disk(self, path: Path) -> bool:
        """Persist cache to disk.

        Args:
            path: Path to save cache file

        Returns:
            True if successful
        """
        try:
            data = {
                "version": 1,
                "saved_at": time.time(),
                "embeddings": {},
                "analyses": {},
            }

            # Save non-expired entries
            with self.embedding_cache._lock:
                for key, entry in self.embedding_cache._cache.items():
                    if not entry.is_expired():
                        data["embeddings"][key] = {
                            "value": entry.value,
                            "created_at": entry.created_at,
                            "ttl": entry.ttl_seconds,
                        }

            with self.analysis_cache._lock:
                for key, entry in self.analysis_cache._cache.items():
                    if not entry.is_expired():
                        data["analyses"][key] = {
                            "value": entry.value,
                            "created_at": entry.created_at,
                            "ttl": entry.ttl_seconds,
                        }

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2))
            self._persistence_path = path
            return True

        except Exception:
            return False

    def load_from_disk(self, path: Path) -> bool:
        """Load cache from disk.

        Args:
            path: Path to load cache file from

        Returns:
            True if successful
        """
        try:
            if not path.exists():
                return False

            data = json.loads(path.read_text())

            if data.get("version") != 1:
                return False

            # Load embeddings
            for key, entry_data in data.get("embeddings", {}).items():
                # Recalculate remaining TTL
                age = time.time() - entry_data["created_at"]
                remaining_ttl = entry_data["ttl"] - age

                if remaining_ttl > 0:
                    self.embedding_cache.set(
                        key, entry_data["value"], ttl=remaining_ttl
                    )

            # Load analyses
            for key, entry_data in data.get("analyses", {}).items():
                age = time.time() - entry_data["created_at"]
                remaining_ttl = entry_data["ttl"] - age

                if remaining_ttl > 0:
                    self.analysis_cache.set(key, entry_data["value"], ttl=remaining_ttl)

            self._persistence_path = path
            return True

        except Exception:
            return False
