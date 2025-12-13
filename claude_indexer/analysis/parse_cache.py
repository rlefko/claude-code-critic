"""AST Parse Cache - Cache parsed entities/relations by file content hash.

Saves 10-15s during re-indexing by skipping re-parsing of unchanged files.
"""

import hashlib
import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from ..indexer_logging import get_logger

if TYPE_CHECKING:
    from .parser import ParserResult


class ParseResultCache:
    """Cache parsed entities/relations/chunks by file content hash.

    Stores serialized ParserResult objects to disk, keyed by content hash.
    When a file's content hash matches a cached entry, parsing is skipped.

    Cache Structure:
        .index_cache/
            parse_cache/
                {model_version}/
                    abc123.json
                    def456.json
    """

    # Increment when parser output format changes to invalidate old cache
    CACHE_VERSION = "v1"

    def __init__(
        self,
        cache_dir: Path | str,
        max_entries: int = 10000,
    ):
        """Initialize parse result cache.

        Args:
            cache_dir: Base directory for cache storage
            max_entries: Maximum number of cached parse results
        """
        self.logger = get_logger()
        self.cache_dir = Path(cache_dir) / "parse_cache" / self.CACHE_VERSION
        self.max_entries = max_entries

        # Thread safety
        self._lock = Lock()

        # In-memory index for fast lookups: {content_hash: metadata}
        self._index: dict[str, dict[str, Any]] = {}

        # Statistics
        self._hits = 0
        self._misses = 0

        # Initialize
        self._init_cache()

    def _init_cache(self) -> None:
        """Initialize cache directory and load index."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_index()
        except Exception as e:
            self.logger.warning(f"Failed to initialize parse cache: {e}")
            self._index = {}

    def _load_index(self) -> None:
        """Scan cache directory to build in-memory index."""
        self._index = {}
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                content_hash = cache_file.stem
                stat = cache_file.stat()
                self._index[content_hash] = {
                    "path": cache_file,
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }
            self.logger.debug(
                f"Loaded parse cache index with {len(self._index)} entries"
            )
        except Exception as e:
            self.logger.warning(f"Failed to load parse cache index: {e}")

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute SHA256 hash of file content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def get(self, content_hash: str) -> dict[str, Any] | None:
        """Get cached parse result by content hash.

        Args:
            content_hash: SHA256 hash of file content

        Returns:
            Serialized ParserResult dict if found, None otherwise
        """
        with self._lock:
            if content_hash not in self._index:
                self._misses += 1
                return None

            cache_file = self._index[content_hash]["path"]

            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    self._hits += 1
                    # Update access time for LRU
                    self._index[content_hash]["last_access"] = time.time()
                    return data
            except Exception as e:
                self.logger.debug(f"Failed to read cached parse result: {e}")
                # Remove corrupted entry
                del self._index[content_hash]
                self._misses += 1
                return None

    def set(self, content_hash: str, result: "ParserResult") -> None:
        """Store parsed result in cache.

        Args:
            content_hash: SHA256 hash of file content
            result: ParserResult to cache
        """
        with self._lock:
            try:
                # Check if we need to evict
                self._maybe_evict()

                # Serialize ParserResult
                serialized = self._serialize_result(result)

                # Write to disk
                cache_file = self.cache_dir / f"{content_hash}.json"
                with open(cache_file, "w") as f:
                    json.dump(serialized, f)

                # Update index
                self._index[content_hash] = {
                    "path": cache_file,
                    "mtime": time.time(),
                    "size": cache_file.stat().st_size,
                    "last_access": time.time(),
                }
            except Exception as e:
                self.logger.debug(f"Failed to cache parse result: {e}")

    def _serialize_result(self, result: "ParserResult") -> dict[str, Any]:
        """Serialize ParserResult to JSON-compatible dict."""
        data: dict[str, Any] = {
            "file_path": str(result.file_path),
            "parsing_time": result.parsing_time,
            "file_hash": result.file_hash,
            "errors": result.errors,
            "warnings": result.warnings,
            "entities": [],
            "relations": [],
            "implementation_chunks": None,
        }

        # Serialize entities
        for entity in result.entities:
            if is_dataclass(entity) and not isinstance(entity, type):
                entity_dict = asdict(entity)
                # Convert Path objects to strings
                if "file_path" in entity_dict and entity_dict["file_path"]:
                    entity_dict["file_path"] = str(entity_dict["file_path"])
                data["entities"].append(entity_dict)

        # Serialize relations
        for relation in result.relations:
            if is_dataclass(relation) and not isinstance(relation, type):
                data["relations"].append(asdict(relation))

        # Serialize implementation chunks if present
        if result.implementation_chunks:
            data["implementation_chunks"] = []
            for chunk in result.implementation_chunks:
                if is_dataclass(chunk) and not isinstance(chunk, type):
                    chunk_dict = asdict(chunk)
                    if "file_path" in chunk_dict and chunk_dict["file_path"]:
                        chunk_dict["file_path"] = str(chunk_dict["file_path"])
                    data["implementation_chunks"].append(chunk_dict)

        return data

    def _maybe_evict(self) -> None:
        """Evict oldest entries if cache exceeds size limit."""
        if len(self._index) < self.max_entries:
            return

        # Sort by last access time (oldest first)
        sorted_entries = sorted(
            self._index.items(),
            key=lambda x: x[1].get("last_access", x[1].get("mtime", 0)),
        )

        # Remove oldest 25%
        entries_to_remove = len(sorted_entries) // 4
        entries_to_remove = max(entries_to_remove, 1)

        for content_hash, entry in sorted_entries[:entries_to_remove]:
            try:
                cache_file = entry["path"]
                if cache_file.exists():
                    cache_file.unlink()
                del self._index[content_hash]
            except Exception as e:
                self.logger.debug(f"Failed to evict cache entry: {e}")

        self.logger.debug(f"Evicted {entries_to_remove} parse cache entries")

    def clear(self) -> None:
        """Clear all cached parse results."""
        with self._lock:
            for entry in self._index.values():
                try:
                    cache_file = entry["path"]
                    if cache_file.exists():
                        cache_file.unlink()
                except Exception:
                    pass

            self._index = {}
            self._hits = 0
            self._misses = 0
            self.logger.info("Cleared parse cache")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._index),
                "max_entries": self.max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": self._hits / total if total > 0 else 0.0,
                "version": self.CACHE_VERSION,
            }

    def __len__(self) -> int:
        """Return number of cached entries."""
        return len(self._index)
