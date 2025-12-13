"""Persistent disk-based embedding cache for reduced API calls and faster re-indexing."""

import contextlib
import hashlib
import json
import struct
import time
from pathlib import Path
from threading import Lock
from typing import Any

from ..indexer_logging import get_logger


class PersistentEmbeddingCache:
    """Disk-based embedding cache with content hash keys.

    Stores embeddings as binary files for efficient storage and retrieval.
    Uses SHA256 content hashes to enable cache hits across re-indexing runs.

    Cache Structure:
        cache_dir/
            index.json          - Hash -> metadata mapping
            embeddings/
                abc123.bin      - Binary embedding vector
                def456.bin
    """

    def __init__(
        self,
        cache_dir: Path | str,
        max_size_mb: int = 500,
        model_name: str = "default",
    ):
        """Initialize persistent embedding cache.

        Args:
            cache_dir: Base directory for cache storage
            max_size_mb: Maximum cache size in megabytes
            model_name: Embedding model name (for cache isolation between models)
        """
        self.logger = get_logger()
        self.cache_dir = Path(cache_dir) / ".embedding_cache" / model_name
        self.embeddings_dir = self.cache_dir / "embeddings"
        self.index_file = self.cache_dir / "index.json"
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.model_name = model_name

        # Thread safety
        self._lock = Lock()

        # In-memory index for fast lookups
        self._index: dict[str, dict[str, Any]] = {}

        # Statistics
        self._hits = 0
        self._misses = 0

        # Initialize cache directory and load index
        self._init_cache()

    def _init_cache(self) -> None:
        """Initialize cache directory structure and load existing index."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.embeddings_dir.mkdir(exist_ok=True)

            if self.index_file.exists():
                with open(self.index_file) as f:
                    self._index = json.load(f)
                self.logger.debug(
                    f"Loaded embedding cache with {len(self._index)} entries"
                )
            else:
                self._index = {}
                self.logger.debug("Initialized new embedding cache")
        except Exception as e:
            self.logger.warning(f"Failed to initialize embedding cache: {e}")
            self._index = {}

    @staticmethod
    def content_hash(content: str) -> str:
        """Generate cache key from content using SHA256.

        Uses first 16 characters of hex digest for reasonable uniqueness
        while keeping filenames manageable.
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def get(self, content_hash: str) -> list[float] | None:
        """Get cached embedding by content hash.

        Args:
            content_hash: SHA256 hash of the original content

        Returns:
            Embedding vector if found, None otherwise
        """
        with self._lock:
            if content_hash not in self._index:
                self._misses += 1
                return None

            entry = self._index[content_hash]
            embedding_file = self.embeddings_dir / f"{content_hash}.bin"

            if not embedding_file.exists():
                # Index entry exists but file is missing - cleanup
                del self._index[content_hash]
                self._misses += 1
                return None

            try:
                embedding = self._read_embedding(embedding_file)
                # Update access time for LRU eviction
                entry["last_access"] = time.time()
                self._hits += 1
                return embedding
            except Exception as e:
                self.logger.warning(f"Failed to read cached embedding: {e}")
                del self._index[content_hash]
                self._misses += 1
                return None

    def get_batch(self, content_hashes: list[str]) -> dict[str, list[float] | None]:
        """Get multiple cached embeddings at once.

        Args:
            content_hashes: List of content hashes to look up

        Returns:
            Dict mapping hash -> embedding (or None if not found)
        """
        results = {}
        for h in content_hashes:
            results[h] = self.get(h)
        return results

    def set(
        self, content_hash: str, embedding: list[float], dimension: int = 0
    ) -> None:
        """Store embedding with automatic eviction if needed.

        Args:
            content_hash: SHA256 hash of the original content
            embedding: Embedding vector to cache
            dimension: Embedding dimension (auto-detected if 0)
        """
        with self._lock:
            try:
                # Check if we need to evict
                self._maybe_evict()

                # Write embedding to binary file
                embedding_file = self.embeddings_dir / f"{content_hash}.bin"
                self._write_embedding(embedding_file, embedding)

                # Update index
                self._index[content_hash] = {
                    "dimension": dimension or len(embedding),
                    "created": time.time(),
                    "last_access": time.time(),
                    "size_bytes": embedding_file.stat().st_size,
                }

                # Periodically save index
                if len(self._index) % 100 == 0:
                    self._save_index()

            except Exception as e:
                self.logger.warning(f"Failed to cache embedding: {e}")

    def set_batch(self, embeddings: dict[str, list[float]], dimension: int = 0) -> None:
        """Store multiple embeddings at once.

        Args:
            embeddings: Dict mapping content_hash -> embedding vector
            dimension: Embedding dimension (auto-detected if 0)
        """
        for content_hash, embedding in embeddings.items():
            self.set(content_hash, embedding, dimension)

        # Save index after batch
        self._save_index()

    def _write_embedding(self, filepath: Path, embedding: list[float]) -> None:
        """Write embedding vector to binary file.

        Uses struct.pack for efficient storage of float32 values.
        """
        with open(filepath, "wb") as f:
            # Write dimension first
            f.write(struct.pack("I", len(embedding)))
            # Write float32 values
            f.write(struct.pack(f"{len(embedding)}f", *embedding))

    def _read_embedding(self, filepath: Path) -> list[float]:
        """Read embedding vector from binary file."""
        with open(filepath, "rb") as f:
            # Read dimension
            dimension = struct.unpack("I", f.read(4))[0]
            # Read float32 values
            embedding = struct.unpack(f"{dimension}f", f.read(dimension * 4))
            return list(embedding)

    def _maybe_evict(self) -> None:
        """Evict oldest entries if cache exceeds size limit."""
        current_size = self._get_cache_size()

        if current_size < self.max_size_bytes:
            return

        # Sort by last access time (oldest first)
        sorted_entries = sorted(
            self._index.items(), key=lambda x: x[1].get("last_access", 0)
        )

        # Remove oldest 25% of entries
        entries_to_remove = len(sorted_entries) // 4
        entries_to_remove = max(entries_to_remove, 1)

        removed_size = 0
        for content_hash, _entry in sorted_entries[:entries_to_remove]:
            embedding_file = self.embeddings_dir / f"{content_hash}.bin"
            try:
                if embedding_file.exists():
                    removed_size += embedding_file.stat().st_size
                    embedding_file.unlink()
                del self._index[content_hash]
            except Exception as e:
                self.logger.warning(f"Failed to evict cache entry {content_hash}: {e}")

        self.logger.info(
            f"Evicted {entries_to_remove} cache entries, freed {removed_size / 1024 / 1024:.1f}MB"
        )

    def _get_cache_size(self) -> int:
        """Calculate total cache size in bytes."""
        total = 0
        for entry in self._index.values():
            total += entry.get("size_bytes", 0)
        return total

    def _save_index(self) -> None:
        """Persist index to disk."""
        try:
            with open(self.index_file, "w") as f:
                json.dump(self._index, f)
        except Exception as e:
            self.logger.warning(f"Failed to save cache index: {e}")

    def flush(self) -> None:
        """Force save index to disk."""
        with self._lock:
            self._save_index()

    def clear(self) -> None:
        """Clear all cached embeddings."""
        with self._lock:
            # Remove all embedding files
            for content_hash in list(self._index.keys()):
                embedding_file = self.embeddings_dir / f"{content_hash}.bin"
                try:
                    if embedding_file.exists():
                        embedding_file.unlink()
                except Exception:
                    pass

            self._index = {}
            self._save_index()
            self._hits = 0
            self._misses = 0
            self.logger.info("Cleared embedding cache")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_ratio = self._hits / total_requests if total_requests > 0 else 0.0
            cache_size = self._get_cache_size()

            return {
                "entries": len(self._index),
                "size_mb": cache_size / 1024 / 1024,
                "max_size_mb": self.max_size_bytes / 1024 / 1024,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": hit_ratio,
                "model": self.model_name,
            }

    def contains(self, content_hash: str) -> bool:
        """Check if content hash exists in cache."""
        with self._lock:
            return content_hash in self._index

    def __len__(self) -> int:
        """Return number of cached embeddings."""
        return len(self._index)

    def __del__(self) -> None:
        """Ensure index is saved on cleanup."""
        with contextlib.suppress(Exception):
            self._save_index()


def get_project_cache_dir(project_path: Path | str) -> Path:
    """Get the cache directory for a project.

    Creates a .index_cache directory in the project root.
    """
    return Path(project_path) / ".index_cache"
