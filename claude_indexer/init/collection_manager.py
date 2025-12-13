"""Qdrant collection management for initialization."""

from ..config.config_loader import ConfigLoader
from ..indexer_logging import get_logger
from .types import InitStepResult

logger = get_logger()


class CollectionManager:
    """Manages Qdrant collection creation for init."""

    # Default vector size for voyage-3.5-lite embeddings
    DEFAULT_VECTOR_SIZE = 1024

    def __init__(self, config_loader: ConfigLoader | None = None):
        """Initialize collection manager.

        Args:
            config_loader: Optional ConfigLoader for Qdrant connection settings.
        """
        self._config_loader = config_loader
        self._store = None
        self._config = None

    def _get_config(self):
        """Get configuration lazily."""
        if self._config is None:
            if self._config_loader:
                self._config = self._config_loader.load()
            else:
                # Try to load from default ConfigLoader
                try:
                    loader = ConfigLoader()
                    self._config = loader.load()
                except Exception as e:
                    logger.debug(f"Could not load config: {e}")
                    self._config = None
        return self._config

    def _get_store(self):
        """Lazy initialization of QdrantStore with graceful failure."""
        if self._store is None:
            try:
                from ..storage.qdrant import QdrantStore

                config = self._get_config()
                if config is None:
                    logger.debug("No config available for Qdrant connection")
                    return None

                self._store = QdrantStore(
                    url=config.qdrant_url,
                    api_key=config.qdrant_api_key,
                )
            except ImportError as e:
                logger.debug(f"Qdrant client not available: {e}")
                return None
            except ConnectionError as e:
                logger.debug(f"Could not connect to Qdrant: {e}")
                return None
            except Exception as e:
                logger.debug(f"Error initializing Qdrant store: {e}")
                return None
        return self._store

    def check_qdrant_available(self) -> bool:
        """Check if Qdrant is accessible.

        Returns:
            True if Qdrant is available and accessible.
        """
        store = self._get_store()
        if store is None:
            return False

        try:
            store.client.get_collections()
            return True
        except Exception as e:
            logger.debug(f"Qdrant health check failed: {e}")
            return False

    def collection_exists(self, collection_name: str) -> bool:
        """Check if collection already exists.

        Args:
            collection_name: Name of the collection to check.

        Returns:
            True if collection exists.
        """
        store = self._get_store()
        if store is None:
            return False

        try:
            return store.collection_exists(collection_name)
        except Exception as e:
            logger.debug(f"Error checking collection existence: {e}")
            return False

    def create_collection(
        self,
        collection_name: str,
        force: bool = False,
        vector_size: int = DEFAULT_VECTOR_SIZE,
    ) -> InitStepResult:
        """Create Qdrant collection for the project.

        Args:
            collection_name: Name of the collection to create.
            force: If True, recreate existing collection.
            vector_size: Size of dense vectors (default: 1024 for voyage-3.5-lite).

        Returns:
            InitStepResult indicating success or failure.
        """
        store = self._get_store()

        if store is None:
            return InitStepResult(
                step_name="qdrant_collection",
                success=True,  # Graceful degradation
                skipped=True,
                warning="Qdrant not available - collection will be created on first index",
                message="Skipped collection creation (Qdrant unavailable)",
            )

        # Check if collection exists
        try:
            exists = store.collection_exists(collection_name)
        except Exception as e:
            return InitStepResult(
                step_name="qdrant_collection",
                success=True,
                skipped=True,
                warning=f"Could not check collection: {e}",
                message="Skipped collection creation (connection error)",
            )

        if exists and not force:
            return InitStepResult(
                step_name="qdrant_collection",
                success=True,
                skipped=True,
                message=f"Collection '{collection_name}' already exists",
            )

        # Delete existing collection if force
        if exists and force:
            try:
                store.delete_collection(collection_name)
                logger.info(f"Deleted existing collection: {collection_name}")
            except Exception as e:
                logger.warning(f"Could not delete existing collection: {e}")

        # Create collection with sparse vectors for hybrid search
        try:
            result = store.create_collection_with_sparse_vectors(
                collection_name=collection_name,
                dense_vector_size=vector_size,
                distance_metric="cosine",
            )

            if result.success:
                return InitStepResult(
                    step_name="qdrant_collection",
                    success=True,
                    message=f"Created collection '{collection_name}' ({vector_size}D vectors)",
                )
            else:
                error_msg = (
                    ", ".join(result.errors) if result.errors else "Unknown error"
                )
                return InitStepResult(
                    step_name="qdrant_collection",
                    success=False,
                    message=f"Failed to create collection: {error_msg}",
                )

        except Exception as e:
            return InitStepResult(
                step_name="qdrant_collection",
                success=False,
                message=f"Error creating collection: {e}",
            )

    def delete_collection(self, collection_name: str) -> InitStepResult:
        """Delete a Qdrant collection.

        Args:
            collection_name: Name of the collection to delete.

        Returns:
            InitStepResult indicating success or failure.
        """
        store = self._get_store()

        if store is None:
            return InitStepResult(
                step_name="delete_collection",
                success=True,
                skipped=True,
                warning="Qdrant not available",
                message="Skipped collection deletion",
            )

        try:
            if not store.collection_exists(collection_name):
                return InitStepResult(
                    step_name="delete_collection",
                    success=True,
                    skipped=True,
                    message=f"Collection '{collection_name}' does not exist",
                )

            result = store.delete_collection(collection_name)
            return InitStepResult(
                step_name="delete_collection",
                success=result.success,
                message=(
                    f"Deleted collection '{collection_name}'"
                    if result.success
                    else f"Failed to delete: {result.errors}"
                ),
            )

        except Exception as e:
            return InitStepResult(
                step_name="delete_collection",
                success=False,
                message=f"Error deleting collection: {e}",
            )

    def get_collection_info(self, collection_name: str) -> dict:
        """Get information about a collection.

        Args:
            collection_name: Name of the collection.

        Returns:
            Dictionary with collection information.
        """
        store = self._get_store()
        info = {
            "name": collection_name,
            "exists": False,
            "qdrant_available": store is not None,
        }

        if store is None:
            return info

        try:
            if store.collection_exists(collection_name):
                info["exists"] = True
                # Get collection details
                collection_info = store.client.get_collection(collection_name)
                info["points_count"] = collection_info.points_count
                info["vectors_count"] = collection_info.vectors_count
        except Exception as e:
            logger.debug(f"Error getting collection info: {e}")

        return info

    def list_all_collections(self) -> list[str]:
        """List all collections from Qdrant.

        Returns:
            List of collection names.
        """
        store = self._get_store()
        if store is None:
            return []

        try:
            return store.list_collections()
        except Exception as e:
            logger.debug(f"Error listing collections: {e}")
            return []

    def list_collections_with_prefix(self, prefix: str) -> list[str]:
        """List collections matching a prefix.

        Args:
            prefix: Prefix to filter by (e.g., "claude").

        Returns:
            List of matching collection names.
        """
        all_collections = self.list_all_collections()
        prefix_pattern = f"{prefix}_"
        return [c for c in all_collections if c.startswith(prefix_pattern)]

    def find_stale_collections(
        self,
        prefix: str = "claude",
        known_project_hashes: list[str] | None = None,
    ) -> list[dict]:
        """Find stale collections that may be orphaned.

        A collection is considered stale if:
        - It matches the prefix pattern
        - Its hash suffix doesn't match any known project

        Args:
            prefix: Collection prefix to filter.
            known_project_hashes: List of known valid project hashes.

        Returns:
            List of dicts with collection name and reason for being stale.
        """
        stale = []
        collections = self.list_collections_with_prefix(prefix)

        for collection_name in collections:
            # Parse collection name: {prefix}_{name}_{hash}
            parts = collection_name.split("_")
            if len(parts) < 3:
                # Old format or malformed - skip
                continue

            collection_hash = parts[-1]

            # Check if hash is known
            if known_project_hashes and collection_hash not in known_project_hashes:
                stale.append(
                    {
                        "name": collection_name,
                        "reason": "Unknown project hash - may be orphaned",
                        "hash": collection_hash,
                    }
                )

        return stale

    def cleanup_collections(
        self,
        collections_to_delete: list[str],
        dry_run: bool = True,
    ) -> InitStepResult:
        """Remove specified collections.

        Args:
            collections_to_delete: List of collection names to delete.
            dry_run: If True, only report what would be deleted.

        Returns:
            InitStepResult with cleanup details.
        """
        if not collections_to_delete:
            return InitStepResult(
                step_name="cleanup_collections",
                success=True,
                message="No collections to clean up",
            )

        if dry_run:
            collection_list = ", ".join(collections_to_delete)
            return InitStepResult(
                step_name="cleanup_collections",
                success=True,
                skipped=True,
                message=f"Would delete {len(collections_to_delete)} collections: {collection_list}",
            )

        store = self._get_store()
        if store is None:
            return InitStepResult(
                step_name="cleanup_collections",
                success=False,
                message="Qdrant not available",
            )

        deleted = []
        errors = []

        for collection_name in collections_to_delete:
            try:
                if store.collection_exists(collection_name):
                    result = store.delete_collection(collection_name)
                    if result.success:
                        deleted.append(collection_name)
                        logger.info(f"Deleted collection: {collection_name}")
                    else:
                        errors.append(f"{collection_name}: {result.errors}")
                else:
                    logger.debug(f"Collection {collection_name} does not exist")
            except Exception as e:
                errors.append(f"{collection_name}: {e}")
                logger.warning(f"Failed to delete {collection_name}: {e}")

        if errors:
            return InitStepResult(
                step_name="cleanup_collections",
                success=False,
                message=f"Deleted {len(deleted)} collections, {len(errors)} errors",
                warning="; ".join(errors),
            )

        return InitStepResult(
            step_name="cleanup_collections",
            success=True,
            message=f"Deleted {len(deleted)} collections",
        )
