#!/usr/bin/env python3
"""
SignatureTableManager - Thread-safe registry for per-collection signature tables.
Enables O(1) duplicate detection across multiple indexed repositories.
"""

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from utils.signature_hash import SignatureHashTable


class SignatureTableManager:
    """Thread-safe registry for per-collection signature tables.

    Manages multiple SignatureHashTable instances, one per collection,
    to support multiple indexed repositories simultaneously.

    Usage:
        manager = SignatureTableManager.get_instance(cache_base)
        table = manager.get_or_create("my-collection")
        manager.update_from_chunk("my-collection", chunk, "function", "/path/to/file.py")
        manager.save_all()
    """

    _instance: "SignatureTableManager | None" = None
    _instance_lock = threading.Lock()

    def __init__(self, cache_base: Path | None = None):
        """Initialize signature table manager.

        Args:
            cache_base: Base directory for collection-specific caches.
                        Defaults to .index_cache/collections in current directory.
        """
        self._tables: dict[str, SignatureHashTable] = {}
        self._lock = threading.Lock()
        self._cache_base = cache_base or Path.cwd() / ".index_cache" / "collections"

    @classmethod
    def get_instance(cls, cache_base: Path | None = None) -> "SignatureTableManager":
        """Get singleton instance for connection reuse.

        Args:
            cache_base: Base directory for caches. Only used on first call.

        Returns:
            Singleton SignatureTableManager instance
        """
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(cache_base)
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.save_all()
            cls._instance = None

    def get_or_create(self, collection_name: str) -> "SignatureHashTable":
        """Get or create signature table for a collection.

        Args:
            collection_name: Name of the collection (e.g., "my-project")

        Returns:
            SignatureHashTable for the collection
        """
        with self._lock:
            if collection_name not in self._tables:
                from utils.signature_hash import SignatureHashTable

                cache_file = (
                    self._cache_base / collection_name / "signature_hashes.json"
                )
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                self._tables[collection_name] = SignatureHashTable(cache_file)
            return self._tables[collection_name]

    def update_from_chunk(
        self,
        collection: str,
        chunk_content: str,
        entity_name: str,
        entity_type: str,
        file_path: str,
    ) -> None:
        """Update signature table from entity chunk content.

        Args:
            collection: Collection name
            chunk_content: The code content from the implementation chunk
            entity_name: Name of the entity (function/class name)
            entity_type: Type of entity ("function", "class", "method")
            file_path: Path to the source file
        """
        if entity_type not in ("function", "class", "method"):
            return

        table = self.get_or_create(collection)
        sig_hash = table.compute_signature(chunk_content, entity_name)
        table.add(sig_hash, entity_name, file_path, entity_type)

    def save_all(self) -> None:
        """Persist all signature tables to disk."""
        with self._lock:
            for table in self._tables.values():
                table.save()

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about managed tables.

        Returns:
            Dictionary with table counts and per-collection stats
        """
        with self._lock:
            stats: dict[str, Any] = {
                "total_collections": len(self._tables),
                "cache_base": str(self._cache_base),
                "collections": {},
            }
            for name, table in self._tables.items():
                stats["collections"][name] = table.get_stats()
            return stats
