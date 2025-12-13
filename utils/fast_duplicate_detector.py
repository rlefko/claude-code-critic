#!/usr/bin/env python3
"""
FastDuplicateDetector - High-performance duplicate detection for Memory Guard Tier 2.
Bypasses Claude CLI for clear-cut duplicate cases using multi-stage detection.

Stages:
1. Signature Hash (O(1), <5ms) - Exact matches
2. BM25 Keyword (<30ms) - High keyword similarity
3. Semantic Search (<100ms) - Vector similarity

Multi-Collection Support:
Uses FastDuplicateDetectorRegistry for per-collection detectors to support
multiple indexed repositories simultaneously.
"""

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DuplicateResult:
    """Result from duplicate detection."""

    decision: str  # "approve", "block", "escalate"
    confidence: float
    reason: str
    matched_entity: str | None = None
    matched_file: str | None = None
    score: float = 0.0
    latency_ms: float = 0.0
    stage: str = ""  # Which stage made the decision
    matches: list[dict[str, Any]] = field(default_factory=list)


class FastDuplicateDetectorRegistry:
    """Thread-safe registry for per-collection duplicate detectors.

    Manages FastDuplicateDetector instances per collection to support
    multiple indexed repositories simultaneously without connection thrashing.

    Usage:
        detector = FastDuplicateDetectorRegistry.get_detector("my-collection", project_root)
        result = detector.check_duplicate(code_info, entities, file_path, "my-collection")
    """

    _detectors: dict[str, "FastDuplicateDetector"] = {}
    _lock = threading.Lock()

    @classmethod
    def get_detector(
        cls, collection: str, project_root: Path | None = None
    ) -> "FastDuplicateDetector":
        """Get or create a detector for the specified collection.

        Args:
            collection: Collection name (e.g., "my-project")
            project_root: Project root for config and cache paths

        Returns:
            FastDuplicateDetector instance for the collection
        """
        with cls._lock:
            if collection not in cls._detectors:
                cls._detectors[collection] = FastDuplicateDetector(
                    collection, project_root
                )
            return cls._detectors[collection]

    @classmethod
    def clear(cls) -> None:
        """Clear all detectors (for testing)."""
        with cls._lock:
            # Save all signature tables before clearing
            for detector in cls._detectors.values():
                detector.save_signature_table()
            cls._detectors.clear()

    @classmethod
    def get_all_stats(cls) -> dict[str, Any]:
        """Get statistics for all registered detectors."""
        with cls._lock:
            return {
                "total_detectors": len(cls._detectors),
                "collections": {
                    name: detector.get_stats()
                    for name, detector in cls._detectors.items()
                },
            }


class FastDuplicateDetector:
    """High-performance duplicate detection bypassing Claude CLI.

    Uses three-stage detection with lazy initialization:
    1. Signature Hash: O(1) exact match via hash table
    2. BM25 Keyword: Local keyword search (no API calls)
    3. Semantic Search: Vector similarity with cached embeddings

    Prefer using FastDuplicateDetectorRegistry.get_detector() for multi-collection support.
    """

    # Confidence thresholds (v4.1 - optimized for fast mode)
    # Tighter thresholds to reduce Tier 3 escalations while maintaining quality
    THRESHOLD_HIGH_BM25 = 0.85  # BM25 score to auto-block
    THRESHOLD_HIGH_SEMANTIC = (
        0.95  # Semantic score to auto-block (unchanged - high confidence)
    )
    THRESHOLD_MEDIUM_SEMANTIC = 0.85  # Was 0.80 - narrower escalation band
    THRESHOLD_APPROVE = 0.55  # Was 0.60 - more aggressive approval

    # Escalation band is now 0.55-0.85 (was 0.60-0.80)
    # This catches clear duplicates while reducing false escalations

    # Latency budgets (ms)
    BUDGET_SIGNATURE = 5
    BUDGET_BM25 = 30
    BUDGET_SEMANTIC = 100
    BUDGET_TOTAL = 200

    # Singleton instance (for backward compatibility)
    _instance: "FastDuplicateDetector | None" = None

    def __init__(self, collection: str | None = None, project_root: Path | None = None):
        """Initialize with lazy-loaded components.

        Args:
            collection: Collection name for collection-specific caching.
                        If None, uses default paths.
            project_root: Project root for config and cache paths.
        """
        # Collection-specific configuration
        self._collection = collection
        self._project_root = project_root or Path.cwd()

        # Lazy-loaded components
        self._qdrant = None
        self._embedder = None
        self._signature_table = None
        self._config = None
        self._initialized = False
        self._init_error: str | None = None

    @classmethod
    def get_instance(cls) -> "FastDuplicateDetector":
        """Get singleton instance for connection reuse.

        Note: Prefer FastDuplicateDetectorRegistry.get_detector() for
        multi-collection support. This method exists for backward compatibility.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _lazy_init(self, collection: str, project_root: Path | None = None) -> bool:
        """Lazily initialize Qdrant, embedder, and signature table.

        Args:
            collection: Qdrant collection name
            project_root: Project root for config loading (uses instance default if None)

        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            return self._init_error is None

        self._initialized = True

        # Use instance values if not provided
        effective_root = project_root or self._project_root or Path.cwd()
        effective_collection = collection or self._collection or "default"

        try:
            from claude_indexer.config.config_loader import ConfigLoader
            from claude_indexer.embeddings.registry import create_embedder_from_config
            from claude_indexer.storage.qdrant import QdrantStore
            from utils.signature_hash import SignatureHashTable

            # Load configuration
            loader = ConfigLoader(effective_root)
            self._config = loader.load()

            # Initialize Qdrant store
            self._qdrant = QdrantStore(
                url=self._config.qdrant_url,
                api_key=self._config.qdrant_api_key,
                collection_name=effective_collection,
            )

            # Initialize embedder with caching
            cache_dir = effective_root / ".index_cache"
            self._embedder = create_embedder_from_config(
                self._config, cache_dir=cache_dir
            )

            # Initialize signature hash table with collection-specific path
            # Use per-collection cache for multi-repo support
            sig_cache_dir = cache_dir / "collections" / effective_collection
            sig_cache_dir.mkdir(parents=True, exist_ok=True)
            sig_cache = sig_cache_dir / "signature_hashes.json"
            self._signature_table = SignatureHashTable(cache_file=sig_cache)

            return True

        except Exception as e:
            self._init_error = str(e)
            return False

    def check_duplicate(
        self,
        code_info: str,
        entity_names: list[str],
        file_path: str,
        collection: str,
        project_root: Path | None = None,
    ) -> DuplicateResult:
        """Multi-stage duplicate detection.

        Args:
            code_info: Formatted code info string
            entity_names: List of entity names to check
            file_path: Path to file being modified
            collection: Qdrant collection name
            project_root: Project root path for config loading

        Returns:
            DuplicateResult with decision, confidence, and details
        """
        start = time.perf_counter()

        # Initialize if needed
        if not self._lazy_init(collection, project_root):
            return DuplicateResult(
                decision="escalate",
                confidence=0.0,
                reason=f"Tier 2 init failed: {self._init_error}",
                stage="init",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        if not entity_names:
            return DuplicateResult(
                decision="escalate",
                confidence=0.0,
                reason="No entities to check",
                stage="init",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        # Stage 1: Signature hash (O(1))
        sig_result = self._check_signature_hash(code_info, entity_names, file_path)
        if sig_result.decision != "escalate":
            sig_result.latency_ms = (time.perf_counter() - start) * 1000
            return sig_result

        # Stage 2: BM25 keyword search (local, no API)
        bm25_result = self._check_bm25(entity_names, collection, file_path)
        if bm25_result.decision != "escalate":
            bm25_result.latency_ms = (time.perf_counter() - start) * 1000
            return bm25_result

        # Stage 3: Semantic search (cached embedding)
        semantic_result = self._check_semantic(
            code_info, entity_names, file_path, collection
        )
        semantic_result.latency_ms = (time.perf_counter() - start) * 1000
        return semantic_result

    def _check_signature_hash(
        self, code_info: str, entity_names: list[str], file_path: str
    ) -> DuplicateResult:
        """Stage 1: O(1) exact duplicate detection using signature hashes.

        Args:
            code_info: Code content
            entity_names: Names of entities to check
            file_path: File being modified

        Returns:
            DuplicateResult - BLOCK on exact match, ESCALATE otherwise
        """
        if self._signature_table is None:
            return DuplicateResult(
                decision="escalate",
                confidence=0.0,
                reason="Signature table not initialized",
                stage="signature",
            )

        for entity_name in entity_names:
            sig_hash = self._signature_table.compute_signature(code_info, entity_name)
            match = self._signature_table.lookup(sig_hash)

            if match is not None:
                # Check if it's the same file (editing existing code)
                if self._is_same_file(match.file_path, file_path):
                    return DuplicateResult(
                        decision="approve",
                        confidence=1.0,
                        reason=f"Modifying existing entity '{entity_name}' in same file",
                        matched_entity=match.entity_name,
                        matched_file=match.file_path,
                        score=1.0,
                        stage="signature",
                    )

                # Exact duplicate in different file
                return DuplicateResult(
                    decision="block",
                    confidence=1.0,
                    reason=f"Exact signature match: '{match.entity_name}' already exists in {match.file_path}",
                    matched_entity=match.entity_name,
                    matched_file=match.file_path,
                    score=1.0,
                    stage="signature",
                )

        # No exact match found
        return DuplicateResult(
            decision="escalate",
            confidence=0.0,
            reason="No exact signature match",
            stage="signature",
        )

    def _check_bm25(
        self, entity_names: list[str], collection: str, file_path: str
    ) -> DuplicateResult:
        """Stage 2: BM25 keyword search (currently skipped, escalates to semantic).

        BM25 requires sparse vector generation which adds complexity.
        For now, we skip directly to semantic search. Can be enabled later
        by generating sparse vectors via BM25Embedder.

        Args:
            entity_names: Names of entities to check
            collection: Collection name
            file_path: File being modified

        Returns:
            DuplicateResult - Always ESCALATE to semantic search
        """
        # Skip BM25 for now - go directly to semantic search
        # TODO: Enable BM25 by generating sparse vectors via BM25Embedder
        return DuplicateResult(
            decision="escalate",
            confidence=0.0,
            reason="BM25 skipped - using semantic search",
            stage="bm25",
        )

    def _check_semantic(
        self,
        code_info: str,
        entity_names: list[str],
        file_path: str,
        collection: str,
    ) -> DuplicateResult:
        """Stage 3: Semantic similarity search with cached embeddings.

        Args:
            code_info: Code content for embedding
            entity_names: Entity names for query construction
            file_path: File being modified
            collection: Qdrant collection

        Returns:
            DuplicateResult - BLOCK/APPROVE/ESCALATE based on similarity
        """
        try:
            if self._qdrant is None or self._embedder is None:
                return DuplicateResult(
                    decision="escalate",
                    confidence=0.0,
                    reason="Qdrant or embedder not initialized",
                    stage="semantic",
                )

            # Build query text - entity names + code snippet
            query_text = " ".join(entity_names) + " " + code_info[:500]

            # Generate embedding (uses cache if available)
            embed_result = self._embedder.embed_text(query_text)
            if not embed_result.success:
                return DuplicateResult(
                    decision="escalate",
                    confidence=0.0,
                    reason=f"Embedding failed: {embed_result.error}",
                    stage="semantic",
                )

            # Search Qdrant with proper interface
            search_result = self._qdrant.search_similar(
                collection_name=collection,
                query_vector=embed_result.embedding,
                limit=5,
                score_threshold=0.5,
                filter_conditions={"chunk_type": "metadata"},
            )

            if not search_result.success or not search_result.results:
                # No matches at all - approve
                return DuplicateResult(
                    decision="approve",
                    confidence=0.0,
                    reason="No semantic matches found - unique code",
                    stage="semantic",
                )

            # Analyze top result
            top = search_result.results[0]
            score = top.get("score", 0.0)
            payload = top.get("payload", {})
            match_name = payload.get("entity_name", "unknown")
            match_file = payload.get("metadata", {}).get("file_path", "")

            # Same file check
            if self._is_same_file(match_file, file_path):
                return DuplicateResult(
                    decision="approve",
                    confidence=score,
                    reason=f"Semantic match in same file (score: {score:.2f})",
                    matched_entity=match_name,
                    matched_file=match_file,
                    score=score,
                    stage="semantic",
                )

            # Decision based on score
            if score >= self.THRESHOLD_HIGH_SEMANTIC:
                return DuplicateResult(
                    decision="block",
                    confidence=score,
                    reason=f"Very high semantic similarity: '{match_name}' (score: {score:.2f})",
                    matched_entity=match_name,
                    matched_file=match_file,
                    score=score,
                    stage="semantic",
                    matches=[
                        {
                            "entity_name": r.get("payload", {}).get("entity_name"),
                            "score": r.get("score"),
                            "file_path": r.get("payload", {})
                            .get("metadata", {})
                            .get("file_path"),
                        }
                        for r in search_result.results[:3]
                    ],
                )

            if score >= self.THRESHOLD_MEDIUM_SEMANTIC:
                # Medium similarity - escalate for AI review
                return DuplicateResult(
                    decision="escalate",
                    confidence=score,
                    reason=f"Medium semantic similarity (score: {score:.2f}) - needs AI review",
                    matched_entity=match_name,
                    matched_file=match_file,
                    score=score,
                    stage="semantic",
                )

            if score < self.THRESHOLD_APPROVE:
                # Low similarity - approve
                return DuplicateResult(
                    decision="approve",
                    confidence=score,
                    reason=f"Low semantic similarity (score: {score:.2f}) - unique code",
                    score=score,
                    stage="semantic",
                )

            # Uncertain zone (0.60 - 0.80) - escalate
            return DuplicateResult(
                decision="escalate",
                confidence=score,
                reason=f"Uncertain semantic match (score: {score:.2f}) - needs AI review",
                matched_entity=match_name,
                matched_file=match_file,
                score=score,
                stage="semantic",
            )

        except Exception as e:
            # On any error, escalate to Tier 3
            return DuplicateResult(
                decision="escalate",
                confidence=0.0,
                reason=f"Semantic search error: {e}",
                stage="semantic",
            )

    def _is_same_file(self, file1: str, file2: str) -> bool:
        """Check if two file paths refer to the same file.

        Args:
            file1: First file path
            file2: Second file path

        Returns:
            True if same file, False otherwise
        """
        if not file1 or not file2:
            return False

        try:
            return Path(file1).resolve() == Path(file2).resolve()
        except Exception:
            return file1 == file2

    def update_signature_table(
        self, entity_name: str, code: str, file_path: str, entity_type: str = "function"
    ) -> None:
        """Add or update an entry in the signature hash table.

        Called after successful code write to keep table current.

        Args:
            entity_name: Name of the entity
            code: Code content
            file_path: File path
            entity_type: Type of entity
        """
        if self._signature_table is None:
            return

        sig_hash = self._signature_table.compute_signature(code, entity_name)
        self._signature_table.add(sig_hash, entity_name, file_path, entity_type)

    def save_signature_table(self) -> None:
        """Persist signature table to disk."""
        if self._signature_table is not None:
            self._signature_table.save()

    def get_stats(self) -> dict[str, Any]:
        """Get detector statistics."""
        stats: dict[str, Any] = {
            "collection": self._collection,
            "project_root": str(self._project_root) if self._project_root else None,
            "initialized": self._initialized,
            "init_error": self._init_error,
            "thresholds": {
                "high_bm25": self.THRESHOLD_HIGH_BM25,
                "high_semantic": self.THRESHOLD_HIGH_SEMANTIC,
                "medium_semantic": self.THRESHOLD_MEDIUM_SEMANTIC,
                "approve": self.THRESHOLD_APPROVE,
            },
        }

        if self._signature_table is not None:
            stats["signature_table"] = self._signature_table.get_stats()

        return stats
