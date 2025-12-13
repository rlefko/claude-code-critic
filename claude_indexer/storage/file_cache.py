"""File content hash cache for incremental re-indexing.

Tracks file content hashes to skip unchanged files during re-indexing,
enabling 90%+ reduction in processing time for incremental updates.
"""

import hashlib
import json
import time
from pathlib import Path
from threading import Lock
from typing import Any

from ..indexer_logging import get_logger


class FileHashCache:
    """Track file content hashes to skip unchanged files.

    Stores SHA256 hashes of file contents indexed against their paths.
    During re-indexing, only files with changed content are processed.

    Cache Structure:
        .index_cache/
            {collection_name}_file_hashes.json
    """

    def __init__(self, project_path: Path | str, collection_name: str):
        """Initialize file hash cache.

        Args:
            project_path: Root directory of the project
            collection_name: Name of the vector collection
        """
        self.logger = get_logger()
        self.project_path = Path(project_path).resolve()
        self.collection_name = collection_name

        # Cache directory
        self.cache_dir = self.project_path / ".index_cache"
        self.cache_file = self.cache_dir / f"{collection_name}_file_hashes.json"

        # Thread safety
        self._lock = Lock()

        # In-memory cache: {relative_path: {"hash": str, "mtime": float, "size": int}}
        self._cache: dict[str, dict[str, Any]] = {}

        # Track changes this session
        self._files_checked = 0
        self._files_changed = 0
        self._files_unchanged = 0

        # Initialize
        self._load_cache()

    def _load_cache(self) -> None:
        """Load existing cache from disk."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            if self.cache_file.exists():
                with open(self.cache_file) as f:
                    data = json.load(f)
                    self._cache = data.get("files", {})
                    self.logger.debug(
                        f"Loaded file hash cache with {len(self._cache)} entries"
                    )
            else:
                self._cache = {}
                self.logger.debug("Initialized new file hash cache")
        except Exception as e:
            self.logger.warning(f"Failed to load file hash cache: {e}")
            self._cache = {}

    def _save_cache(self) -> None:
        """Persist cache to disk."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            data = {
                "collection": self.collection_name,
                "project_path": str(self.project_path),
                "updated_at": time.time(),
                "files": self._cache,
            }

            with open(self.cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save file hash cache: {e}")

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute SHA256 hash of file contents.

        Args:
            file_path: Path to the file

        Returns:
            First 16 characters of SHA256 hex digest
        """
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                # Read in chunks for large files
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()[:16]
        except Exception:
            return ""

    def get_relative_path(self, file_path: Path) -> str:
        """Get path relative to project root."""
        try:
            return str(file_path.resolve().relative_to(self.project_path))
        except ValueError:
            return str(file_path)

    def has_changed(self, file_path: Path) -> bool:
        """Check if file has changed since last indexing.

        Uses a two-tier check:
        1. Fast: mtime + size comparison
        2. Slow: content hash (only if fast check is ambiguous)

        Args:
            file_path: Path to check

        Returns:
            True if file needs re-indexing, False if unchanged
        """
        with self._lock:
            self._files_checked += 1
            rel_path = self.get_relative_path(file_path)

            # New file - definitely changed
            if rel_path not in self._cache:
                self._files_changed += 1
                return True

            cached = self._cache[rel_path]

            try:
                stat = file_path.stat()
                current_mtime = stat.st_mtime
                current_size = stat.st_size

                # Fast path: if mtime and size match, likely unchanged
                if (
                    cached.get("mtime") == current_mtime
                    and cached.get("size") == current_size
                ):
                    self._files_unchanged += 1
                    return False

                # Slow path: compute content hash
                current_hash = self.compute_file_hash(file_path)

                if current_hash == cached.get("hash"):
                    # Content unchanged despite mtime/size change
                    # Update mtime/size for faster future checks
                    cached["mtime"] = current_mtime
                    cached["size"] = current_size
                    self._files_unchanged += 1
                    return False

                # Content actually changed
                self._files_changed += 1
                return True

            except Exception as e:
                self.logger.debug(f"Error checking file {file_path}: {e}")
                self._files_changed += 1
                return True

    def get_changed_files(self, files: list[Path]) -> list[Path]:
        """Filter list to only files that have changed.

        Args:
            files: List of file paths to check

        Returns:
            List of files that need re-indexing
        """
        changed = []
        for file_path in files:
            if self.has_changed(file_path):
                changed.append(file_path)

        if files:
            hit_ratio = (len(files) - len(changed)) / len(files)
            self.logger.info(
                f"File cache: {len(files) - len(changed)}/{len(files)} unchanged "
                f"({hit_ratio * 100:.0f}% cache hit rate)"
            )

        return changed

    def update(self, file_path: Path) -> None:
        """Update cache entry for a file after successful indexing.

        Args:
            file_path: Path to the indexed file
        """
        with self._lock:
            try:
                stat = file_path.stat()
                rel_path = self.get_relative_path(file_path)

                self._cache[rel_path] = {
                    "hash": self.compute_file_hash(file_path),
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                    "indexed_at": time.time(),
                }
            except Exception as e:
                self.logger.debug(f"Failed to update cache for {file_path}: {e}")

    def update_batch(self, files: list[Path]) -> None:
        """Update cache entries for multiple files.

        Args:
            files: List of successfully indexed files
        """
        for file_path in files:
            self.update(file_path)

        # Save cache after batch update
        self._save_cache()

    def remove(self, file_path: Path) -> None:
        """Remove file from cache (e.g., when deleted).

        Args:
            file_path: Path to remove from cache
        """
        with self._lock:
            rel_path = self.get_relative_path(file_path)
            self._cache.pop(rel_path, None)

    def flush(self) -> None:
        """Force save cache to disk."""
        with self._lock:
            self._save_cache()

    def clear(self) -> None:
        """Clear all cached hashes (forces full re-index)."""
        with self._lock:
            self._cache = {}
            self._save_cache()
            self.logger.info("Cleared file hash cache")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._files_checked
            return {
                "cached_files": len(self._cache),
                "files_checked": self._files_checked,
                "files_changed": self._files_changed,
                "files_unchanged": self._files_unchanged,
                "hit_ratio": self._files_unchanged / total if total > 0 else 0.0,
                "collection": self.collection_name,
            }

    def get_deleted_files(self, current_files: set[Path]) -> list[str]:
        """Find files in cache that no longer exist.

        Args:
            current_files: Set of currently existing file paths

        Returns:
            List of relative paths for deleted files
        """
        current_rel_paths = {self.get_relative_path(f) for f in current_files}
        deleted = []

        with self._lock:
            for cached_path in list(self._cache.keys()):
                if cached_path not in current_rel_paths:
                    deleted.append(cached_path)
                    del self._cache[cached_path]

        return deleted

    def __len__(self) -> int:
        """Return number of cached file entries."""
        return len(self._cache)
