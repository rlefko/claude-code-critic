"""Caching infrastructure for CI audit fingerprints.

This module provides caching for style and component fingerprints to
improve performance of repeated CI audit runs.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import UIQualityConfig
    from ..models import StaticComponentFingerprint, StyleFingerprint


@dataclass
class CacheEntry:
    """Cached fingerprints for a single file."""

    file_path: str
    content_hash: str  # SHA256 of file content
    style_fingerprints: list[dict[str, Any]] = field(default_factory=list)
    component_fingerprints: list[dict[str, Any]] = field(default_factory=list)
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "content_hash": self.content_hash,
            "style_fingerprints": self.style_fingerprints,
            "component_fingerprints": self.component_fingerprints,
            "extracted_at": self.extracted_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CacheEntry":
        """Create from dictionary."""
        return cls(
            file_path=data["file_path"],
            content_hash=data["content_hash"],
            style_fingerprints=data.get("style_fingerprints", []),
            component_fingerprints=data.get("component_fingerprints", []),
            extracted_at=data.get("extracted_at", datetime.now().isoformat()),
        )


@dataclass
class CacheMetadata:
    """Cache metadata for invalidation tracking."""

    version: str = "1.0"
    project_path: str = ""
    config_hash: str = ""  # Hash of UI config for invalidation
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    total_entries: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "project_path": self.project_path,
            "config_hash": self.config_hash,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "total_entries": self.total_entries,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CacheMetadata":
        """Create from dictionary."""
        return cls(
            version=data.get("version", "1.0"),
            project_path=data.get("project_path", ""),
            config_hash=data.get("config_hash", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_accessed=data.get("last_accessed", datetime.now().isoformat()),
            total_entries=data.get("total_entries", 0),
        )


class FingerprintCache:
    """Per-file fingerprint cache stored in .ui-quality/cache/.

    This cache stores extracted fingerprints keyed by file path and
    content hash, allowing fast retrieval of fingerprints when files
    haven't changed.
    """

    CACHE_DIR = ".ui-quality/cache"
    ENTRIES_FILE = "fingerprints.json"
    METADATA_FILE = "metadata.json"
    CACHE_VERSION = "1.0"

    def __init__(self, project_path: Path, config: "UIQualityConfig"):
        """Initialize the fingerprint cache.

        Args:
            project_path: Root path of the project.
            config: UI quality configuration.
        """
        self.project_path = Path(project_path)
        self.config = config
        self.cache_dir = self.project_path / self.CACHE_DIR
        self._entries: dict[str, CacheEntry] = {}
        self._metadata: CacheMetadata | None = None
        self._dirty = False

    @property
    def config_hash(self) -> str:
        """Compute hash of current config for invalidation."""
        config_str = json.dumps(
            {
                "similarity_thresholds": {
                    "duplicate": self.config.gating.similarity_thresholds.duplicate,
                    "near_duplicate": self.config.gating.similarity_thresholds.near_duplicate,
                },
                "min_confidence": self.config.gating.min_confidence,
            },
            sort_keys=True,
        )
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

    def load(self) -> bool:
        """Load cache from disk.

        Returns:
            True if cache was loaded successfully, False otherwise.
        """
        metadata_path = self.cache_dir / self.METADATA_FILE
        entries_path = self.cache_dir / self.ENTRIES_FILE

        if not metadata_path.exists() or not entries_path.exists():
            return False

        try:
            # Load metadata
            with open(metadata_path) as f:
                metadata_data = json.load(f)
                self._metadata = CacheMetadata.from_dict(metadata_data)

            # Check version compatibility
            if self._metadata.version != self.CACHE_VERSION:
                self.clear()
                return False

            # Check config hash for invalidation
            if self._metadata.config_hash != self.config_hash:
                self.clear()
                return False

            # Load entries
            with open(entries_path) as f:
                entries_data = json.load(f)
                self._entries = {
                    path: CacheEntry.from_dict(entry)
                    for path, entry in entries_data.items()
                }

            # Update last accessed
            self._metadata.last_accessed = datetime.now().isoformat()
            self._dirty = True

            return True

        except (json.JSONDecodeError, KeyError, TypeError):
            self.clear()
            return False

    def save(self) -> None:
        """Persist cache to disk."""
        if not self._dirty:
            return

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Update metadata
        if self._metadata is None:
            self._metadata = CacheMetadata(
                project_path=str(self.project_path),
                config_hash=self.config_hash,
            )

        self._metadata.total_entries = len(self._entries)
        self._metadata.last_accessed = datetime.now().isoformat()

        # Save metadata
        metadata_path = self.cache_dir / self.METADATA_FILE
        with open(metadata_path, "w") as f:
            json.dump(self._metadata.to_dict(), f, indent=2)

        # Save entries
        entries_path = self.cache_dir / self.ENTRIES_FILE
        entries_data = {path: entry.to_dict() for path, entry in self._entries.items()}
        with open(entries_path, "w") as f:
            json.dump(entries_data, f, indent=2)

        self._dirty = False

    def get(self, file_path: Path, content_hash: str) -> CacheEntry | None:
        """Get cached fingerprints if valid.

        Args:
            file_path: Path to the file.
            content_hash: SHA256 hash of file content.

        Returns:
            CacheEntry if found and valid, None otherwise.
        """
        path_key = str(file_path)
        entry = self._entries.get(path_key)

        if entry is None:
            return None

        # Validate content hash
        if entry.content_hash != content_hash:
            # Invalidate stale entry
            del self._entries[path_key]
            self._dirty = True
            return None

        return entry

    def set(
        self,
        file_path: Path,
        content_hash: str,
        style_fingerprints: list["StyleFingerprint"],
        component_fingerprints: list["StaticComponentFingerprint"],
    ) -> None:
        """Store fingerprints in cache.

        Args:
            file_path: Path to the file.
            content_hash: SHA256 hash of file content.
            style_fingerprints: Extracted style fingerprints.
            component_fingerprints: Extracted component fingerprints.
        """
        path_key = str(file_path)

        # Serialize fingerprints to dicts
        style_dicts = [fp.to_dict() for fp in style_fingerprints]
        component_dicts = [fp.to_dict() for fp in component_fingerprints]

        self._entries[path_key] = CacheEntry(
            file_path=path_key,
            content_hash=content_hash,
            style_fingerprints=style_dicts,
            component_fingerprints=component_dicts,
        )
        self._dirty = True

    def invalidate(self, file_path: Path) -> None:
        """Invalidate cache for a specific file.

        Args:
            file_path: Path to the file to invalidate.
        """
        path_key = str(file_path)
        if path_key in self._entries:
            del self._entries[path_key]
            self._dirty = True

    def clear(self) -> None:
        """Clear entire cache."""
        self._entries.clear()
        self._metadata = None
        self._dirty = True

        # Remove cache files
        if self.cache_dir.exists():
            for file in [self.ENTRIES_FILE, self.METADATA_FILE]:
                file_path = self.cache_dir / file
                if file_path.exists():
                    file_path.unlink()

    @property
    def size(self) -> int:
        """Number of entries in cache."""
        return len(self._entries)

    @property
    def entries(self) -> dict[str, CacheEntry]:
        """All cache entries."""
        return self._entries.copy()


class CacheManager:
    """Manages caching for full CI audit runs.

    Coordinates fingerprint caching with file content hashing and
    provides an interface for the audit runner.
    """

    def __init__(self, project_path: Path, config: "UIQualityConfig"):
        """Initialize the cache manager.

        Args:
            project_path: Root path of the project.
            config: UI quality configuration.
        """
        self.project_path = Path(project_path)
        self.config = config
        self.fingerprint_cache = FingerprintCache(project_path, config)
        self._loaded = False
        self._hits = 0
        self._misses = 0

    def initialize(self) -> None:
        """Load cache from disk if available."""
        if not self._loaded:
            self.fingerprint_cache.load()
            self._loaded = True

    def finalize(self) -> None:
        """Save cache to disk."""
        self.fingerprint_cache.save()

    def get_content_hash(self, file_path: Path) -> str:
        """Compute content hash for a file.

        Args:
            file_path: Path to the file.

        Returns:
            SHA256 hash of file content.
        """
        try:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return ""

    def get_cached_fingerprints(
        self, file_path: Path
    ) -> tuple[list["StyleFingerprint"], list["StaticComponentFingerprint"]] | None:
        """Get cached fingerprints for a file.

        Args:
            file_path: Path to the file.

        Returns:
            Tuple of (style_fingerprints, component_fingerprints) if cached,
            None if not cached or invalid.
        """
        self.initialize()

        content_hash = self.get_content_hash(file_path)
        if not content_hash:
            self._misses += 1
            return None

        entry = self.fingerprint_cache.get(file_path, content_hash)
        if entry is None:
            self._misses += 1
            return None

        # Deserialize fingerprints
        from ..models import StaticComponentFingerprint, StyleFingerprint

        styles = [StyleFingerprint.from_dict(d) for d in entry.style_fingerprints]
        components = [
            StaticComponentFingerprint.from_dict(d)
            for d in entry.component_fingerprints
        ]

        self._hits += 1
        return (styles, components)

    def cache_fingerprints(
        self,
        file_path: Path,
        style_fingerprints: list["StyleFingerprint"],
        component_fingerprints: list["StaticComponentFingerprint"],
    ) -> None:
        """Cache fingerprints for a file.

        Args:
            file_path: Path to the file.
            style_fingerprints: Extracted style fingerprints.
            component_fingerprints: Extracted component fingerprints.
        """
        self.initialize()

        content_hash = self.get_content_hash(file_path)
        if not content_hash:
            return

        self.fingerprint_cache.set(
            file_path, content_hash, style_fingerprints, component_fingerprints
        )

    def invalidate(self, file_path: Path) -> None:
        """Invalidate cache for a file.

        Args:
            file_path: Path to the file.
        """
        self.fingerprint_cache.invalidate(file_path)

    def clear(self) -> None:
        """Clear all cached data."""
        self.fingerprint_cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0 to 1.0)."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    @property
    def stats(self) -> dict[str, Any]:
        """Cache statistics."""
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
            "size": self.fingerprint_cache.size,
        }


__all__ = [
    "CacheEntry",
    "CacheMetadata",
    "FingerprintCache",
    "CacheManager",
]
