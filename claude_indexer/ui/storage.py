"""Qdrant storage for UI consistency checking.

This module provides UI-specific Qdrant collection management
and payload schemas for storing UI component fingerprints.
"""

from typing import Any

from ..indexer_logging import get_logger
from .models import (
    RuntimeElementFingerprint,
    StaticComponentFingerprint,
    StyleFingerprint,
    SymbolKind,
)

logger = get_logger()

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        SparseVectorParams,
        VectorParams,
        VectorsConfig,
    )

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    QdrantClient = Any
    Distance = Any
    VectorParams = Any
    SparseVectorParams = Any
    VectorsConfig = Any
    PointStruct = Any
    Filter = Any
    FieldCondition = Any
    MatchValue = Any

# UI collection names
UI_SYMBOLS_COLLECTION = "ui_symbols"
UI_STYLES_COLLECTION = "ui_styles"
UI_RUNTIME_COLLECTION = "ui_runtime_snapshots"

# Default vector dimensions
DEFAULT_DENSE_DIM = 512  # Voyage AI default
DEFAULT_SPARSE_DIM = 30000  # BM25 vocabulary size


class UICollectionManager:
    """Manager for UI-specific Qdrant collections.

    Handles creation, migration, and schema management for
    UI component and style collections.
    """

    def __init__(
        self,
        client: "QdrantClient",
        dense_dim: int = DEFAULT_DENSE_DIM,
    ):
        """Initialize the collection manager.

        Args:
            client: Qdrant client instance.
            dense_dim: Dimension for dense vectors (512 for Voyage, 1536 for OpenAI).
        """
        if not QDRANT_AVAILABLE:
            raise ImportError(
                "qdrant-client is required for UI storage. "
                "Install it with: pip install qdrant-client"
            )

        self.client = client
        self.dense_dim = dense_dim

    def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists.

        Args:
            collection_name: Name of the collection.

        Returns:
            True if the collection exists.
        """
        try:
            collections = self.client.get_collections().collections
            return any(c.name == collection_name for c in collections)
        except Exception as e:
            logger.warning(f"Error checking collection existence: {e}")
            return False

    def create_ui_symbols_collection(
        self,
        collection_name: str = UI_SYMBOLS_COLLECTION,
        force_recreate: bool = False,
    ) -> bool:
        """Create the UI symbols collection for component fingerprints.

        Args:
            collection_name: Name for the collection.
            force_recreate: If True, delete and recreate existing collection.

        Returns:
            True if collection was created, False if it already existed.
        """
        if self.collection_exists(collection_name):
            if force_recreate:
                logger.info(f"Recreating collection {collection_name}")
                self.client.delete_collection(collection_name)
            else:
                logger.debug(f"Collection {collection_name} already exists")
                return False

        logger.info(f"Creating UI symbols collection: {collection_name}")

        # Create with hybrid vector support (dense + sparse)
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": VectorParams(
                    size=self.dense_dim,
                    distance=Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                "bm25": SparseVectorParams(),
            },
        )

        # Create payload indexes for fast filtering
        self._create_ui_payload_indexes(collection_name)

        logger.info(f"Created UI symbols collection with {self.dense_dim}D vectors")
        return True

    def create_ui_styles_collection(
        self,
        collection_name: str = UI_STYLES_COLLECTION,
        force_recreate: bool = False,
    ) -> bool:
        """Create the UI styles collection for style fingerprints.

        This collection uses exact and near-hash matching rather than
        vector similarity, so it has simpler configuration.

        Args:
            collection_name: Name for the collection.
            force_recreate: If True, delete and recreate existing collection.

        Returns:
            True if collection was created, False if it already existed.
        """
        if self.collection_exists(collection_name):
            if force_recreate:
                logger.info(f"Recreating collection {collection_name}")
                self.client.delete_collection(collection_name)
            else:
                logger.debug(f"Collection {collection_name} already exists")
                return False

        logger.info(f"Creating UI styles collection: {collection_name}")

        # Styles collection uses smaller vectors (hash-based similarity)
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=128,  # Smaller vectors for hash-based similarity
                distance=Distance.COSINE,
            ),
        )

        # Create payload indexes
        self._create_style_payload_indexes(collection_name)

        logger.info("Created UI styles collection")
        return True

    def create_ui_runtime_collection(
        self,
        collection_name: str = UI_RUNTIME_COLLECTION,
        force_recreate: bool = False,
    ) -> bool:
        """Create the UI runtime collection for Playwright snapshots.

        Args:
            collection_name: Name for the collection.
            force_recreate: If True, delete and recreate existing collection.

        Returns:
            True if collection was created, False if it already existed.
        """
        if self.collection_exists(collection_name):
            if force_recreate:
                logger.info(f"Recreating collection {collection_name}")
                self.client.delete_collection(collection_name)
            else:
                logger.debug(f"Collection {collection_name} already exists")
                return False

        logger.info(f"Creating UI runtime collection: {collection_name}")

        # Runtime collection for element fingerprints
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": VectorParams(
                    size=self.dense_dim,
                    distance=Distance.COSINE,
                ),
            },
        )

        # Create payload indexes
        self._create_runtime_payload_indexes(collection_name)

        logger.info("Created UI runtime collection")
        return True

    def _create_ui_payload_indexes(self, collection_name: str) -> None:
        """Create payload indexes for UI symbols collection."""
        indexes = [
            ("type", "keyword"),
            ("kind", "keyword"),
            ("name", "keyword"),
            ("file_path", "keyword"),
            ("framework", "keyword"),
            ("structure_hash", "keyword"),
        ]

        for field_name, field_type in indexes:
            try:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_type,
                )
            except Exception as e:
                logger.debug(f"Index {field_name} may already exist: {e}")

    def _create_style_payload_indexes(self, collection_name: str) -> None:
        """Create payload indexes for UI styles collection."""
        indexes = [
            ("exact_hash", "keyword"),
            ("near_hash", "keyword"),
            ("file_path", "keyword"),
        ]

        for field_name, field_type in indexes:
            try:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_type,
                )
            except Exception as e:
                logger.debug(f"Index {field_name} may already exist: {e}")

    def _create_runtime_payload_indexes(self, collection_name: str) -> None:
        """Create payload indexes for UI runtime collection."""
        indexes = [
            ("page_id", "keyword"),
            ("role", "keyword"),
            ("screenshot_hash", "keyword"),
        ]

        for field_name, field_type in indexes:
            try:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_type,
                )
            except Exception as e:
                logger.debug(f"Index {field_name} may already exist: {e}")


def create_component_payload(
    fingerprint: StaticComponentFingerprint,
    framework: str = "unknown",
    name: str | None = None,
) -> dict[str, Any]:
    """Create a Qdrant payload from a component fingerprint.

    Args:
        fingerprint: The component fingerprint.
        framework: Framework name (react, vue, svelte).
        name: Optional component name.

    Returns:
        Payload dictionary for Qdrant.
    """
    payload = {
        "type": "ui_component",
        "kind": SymbolKind.COMPONENT.value,
        "structure_hash": fingerprint.structure_hash,
        "style_refs": fingerprint.style_refs,
        "framework": framework,
    }

    if name:
        payload["name"] = name

    if fingerprint.prop_shape_sketch:
        payload["prop_shape"] = fingerprint.prop_shape_sketch

    if fingerprint.source_ref:
        payload["file_path"] = fingerprint.source_ref.file_path
        payload["start_line"] = fingerprint.source_ref.start_line
        payload["end_line"] = fingerprint.source_ref.end_line

    return payload


def create_style_payload(fingerprint: StyleFingerprint) -> dict[str, Any]:
    """Create a Qdrant payload from a style fingerprint.

    Args:
        fingerprint: The style fingerprint.

    Returns:
        Payload dictionary for Qdrant.
    """
    payload = {
        "type": "ui_style",
        "kind": SymbolKind.CSS.value,
        "exact_hash": fingerprint.exact_hash,
        "near_hash": fingerprint.near_hash,
        "declaration_set": fingerprint.declaration_set,
        "tokens_used": fingerprint.tokens_used,
    }

    if fingerprint.source_refs:
        # Store first source ref as primary location
        primary = fingerprint.source_refs[0]
        payload["file_path"] = primary.file_path
        payload["start_line"] = primary.start_line
        payload["end_line"] = primary.end_line

        # Store all source refs for deduplication tracking
        payload["source_refs"] = [ref.to_dict() for ref in fingerprint.source_refs]

    return payload


def create_runtime_payload(fingerprint: RuntimeElementFingerprint) -> dict[str, Any]:
    """Create a Qdrant payload from a runtime element fingerprint.

    Args:
        fingerprint: The runtime element fingerprint.

    Returns:
        Payload dictionary for Qdrant.
    """
    payload = {
        "type": "ui_element",
        "page_id": fingerprint.page_id,
        "selector": fingerprint.selector,
        "role": fingerprint.role,
        "computed_style": fingerprint.computed_style_subset,
    }

    if fingerprint.screenshot_hash:
        payload["screenshot_hash"] = fingerprint.screenshot_hash

    if fingerprint.source_map_hint:
        payload["source_map_hint"] = fingerprint.source_map_hint

    if fingerprint.layout_box:
        payload["layout_box"] = fingerprint.layout_box.to_dict()

    return payload


def generate_ui_point_id(
    fingerprint_type: str,
    identifier: str,
    file_path: str | None = None,
) -> str:
    """Generate a deterministic point ID for UI fingerprints.

    Args:
        fingerprint_type: Type of fingerprint (component, style, element).
        identifier: Unique identifier (e.g., structure_hash, exact_hash).
        file_path: Optional file path for additional uniqueness.

    Returns:
        SHA256-based point ID.
    """
    import hashlib

    content = f"{fingerprint_type}::{identifier}"
    if file_path:
        content += f"::{file_path}"

    return hashlib.sha256(content.encode()).hexdigest()[:32]
