#!/usr/bin/env python3
"""
SignatureHashTable - O(1) lookup table for function/class signatures.
Used by Memory Guard Tier 2 for exact duplicate detection.
"""

import hashlib
import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from re import Pattern
from typing import Any


@dataclass
class SignatureEntry:
    """Entry in the signature hash table."""

    entity_name: str
    file_path: str
    signature_hash: str
    entity_type: str  # "function", "class", "method"
    created_at: str


class SignatureHashTable:
    """O(1) lookup table for function/class signatures.

    Signatures are normalized to ignore:
    - Whitespace variations
    - Default parameter values
    - Docstrings
    - Type hint formatting differences

    Signatures include:
    - Entity name
    - Parameter count and names (sorted)
    - Return type (if present)
    - Entity type (function/class/method)
    """

    def __init__(self, cache_file: Path | str | None = None):
        """Initialize signature hash table.

        Args:
            cache_file: Path to persist hash table. If None, memory-only.
        """
        self._hash_table: dict[str, SignatureEntry] = {}
        self._cache_file = Path(cache_file) if cache_file else None
        self._lock = threading.Lock()

        # Pre-compiled regex patterns for signature extraction
        self._func_pattern: Pattern = re.compile(
            r"^\s*(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*([^:]+))?:",
            re.MULTILINE,
        )
        self._class_pattern: Pattern = re.compile(
            r"^\s*class\s+(\w+)\s*(?:\(([^)]*)\))?:", re.MULTILINE
        )
        self._method_pattern: Pattern = re.compile(
            r"^\s*(?:async\s+)?def\s+(\w+)\s*\(\s*self\s*,?([^)]*)\)(?:\s*->\s*([^:]+))?:",
            re.MULTILINE,
        )

        # Load from disk if cache file exists
        if self._cache_file:
            self.load()

    def compute_signature(self, code: str, entity_name: str) -> str:
        """Extract normalized signature for hashing.

        Args:
            code: Code content containing the entity
            entity_name: Name of the entity to extract signature for

        Returns:
            16-character SHA256 hash of normalized signature
        """
        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", code.strip())

        # Try to extract function signature
        func_match = self._func_pattern.search(normalized)
        if func_match and func_match.group(1) == entity_name:
            name = func_match.group(1)
            params = func_match.group(2) or ""
            return_type = func_match.group(3) or "None"

            # Extract parameter names (ignore types, defaults)
            param_names = self._extract_param_names(params, exclude_self=False)

            # Build signature string
            sig_str = f"function|{name}|{len(param_names)}|{','.join(sorted(param_names))}|{return_type.strip()}"
            return hashlib.sha256(sig_str.encode()).hexdigest()[:16]

        # Try to extract method signature (has self)
        method_match = self._method_pattern.search(normalized)
        if method_match and method_match.group(1) == entity_name:
            name = method_match.group(1)
            params = method_match.group(2) or ""
            return_type = method_match.group(3) or "None"

            param_names = self._extract_param_names(params, exclude_self=True)

            sig_str = f"method|{name}|{len(param_names)}|{','.join(sorted(param_names))}|{return_type.strip()}"
            return hashlib.sha256(sig_str.encode()).hexdigest()[:16]

        # Try to extract class signature
        class_match = self._class_pattern.search(normalized)
        if class_match and class_match.group(1) == entity_name:
            name = class_match.group(1)
            bases = class_match.group(2) or ""

            # Normalize base classes
            base_list = [b.strip() for b in bases.split(",") if b.strip()]

            sig_str = f"class|{name}|{','.join(sorted(base_list))}"
            return hashlib.sha256(sig_str.encode()).hexdigest()[:16]

        # Fallback: hash entity name + first 100 chars of normalized code
        fallback_str = f"unknown|{entity_name}|{normalized[:100]}"
        return hashlib.sha256(fallback_str.encode()).hexdigest()[:16]

    def _extract_param_names(
        self, params: str, exclude_self: bool = False
    ) -> list[str]:
        """Extract parameter names from parameter string.

        Args:
            params: Parameter string like "a, b: int, c=5"
            exclude_self: Whether to exclude 'self' parameter

        Returns:
            List of parameter names
        """
        param_names = []
        for param in params.split(","):
            param = param.strip()
            if not param:
                continue

            # Extract just the name (before : or =)
            name = param.split(":")[0].split("=")[0].strip()

            # Handle *args and **kwargs
            name = name.lstrip("*")

            if name and (not exclude_self or name != "self"):
                param_names.append(name)

        return param_names

    def lookup(self, signature_hash: str) -> SignatureEntry | None:
        """O(1) lookup for exact signature match.

        Args:
            signature_hash: 16-character signature hash

        Returns:
            SignatureEntry if found, None otherwise
        """
        with self._lock:
            return self._hash_table.get(signature_hash)

    def add(
        self,
        signature_hash: str,
        entity_name: str,
        file_path: str,
        entity_type: str = "function",
    ) -> None:
        """Add signature to hash table.

        Args:
            signature_hash: 16-character signature hash
            entity_name: Name of the entity
            file_path: Path to file containing entity
            entity_type: Type of entity (function, class, method)
        """
        with self._lock:
            self._hash_table[signature_hash] = SignatureEntry(
                entity_name=entity_name,
                file_path=str(file_path),
                signature_hash=signature_hash,
                entity_type=entity_type,
                created_at=datetime.now().isoformat(),
            )

    def remove(self, signature_hash: str) -> bool:
        """Remove signature from hash table.

        Args:
            signature_hash: Hash to remove

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if signature_hash in self._hash_table:
                del self._hash_table[signature_hash]
                return True
            return False

    def load(self) -> None:
        """Load hash table from disk cache."""
        if not self._cache_file or not self._cache_file.exists():
            return

        try:
            with self._lock:
                with open(self._cache_file) as f:
                    data = json.load(f)

                self._hash_table = {}
                for sig_hash, entry_data in data.items():
                    self._hash_table[sig_hash] = SignatureEntry(**entry_data)

        except Exception:
            # If loading fails, start with empty table
            self._hash_table = {}

    def save(self) -> None:
        """Persist hash table to disk (atomic write)."""
        if not self._cache_file:
            return

        try:
            with self._lock:
                # Ensure parent directory exists
                self._cache_file.parent.mkdir(parents=True, exist_ok=True)

                # Serialize entries
                data = {k: asdict(v) for k, v in self._hash_table.items()}

                # Atomic write via temp file
                temp_file = self._cache_file.with_suffix(".tmp")
                with open(temp_file, "w") as f:
                    json.dump(data, f, indent=2)

                temp_file.rename(self._cache_file)

        except Exception:
            # Silently fail on save errors
            pass

    def clear(self) -> None:
        """Clear all entries from hash table."""
        with self._lock:
            self._hash_table = {}

    def size(self) -> int:
        """Return number of entries in hash table."""
        return len(self._hash_table)

    def get_stats(self) -> dict[str, Any]:
        """Get hash table statistics."""
        with self._lock:
            entity_types: dict[str, int] = {}
            for entry in self._hash_table.values():
                entity_types[entry.entity_type] = (
                    entity_types.get(entry.entity_type, 0) + 1
                )

            return {
                "total_entries": len(self._hash_table),
                "entity_types": entity_types,
                "cache_file": str(self._cache_file) if self._cache_file else None,
            }
