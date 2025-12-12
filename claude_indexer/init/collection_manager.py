"""Qdrant collection management for initialization."""

from typing import Optional

from ..config.config_loader import ConfigLoader
from ..indexer_logging import get_logger
from .types import InitStepResult

logger = get_logger()


class CollectionManager:
    """Manages Qdrant collection creation for init."""

    # Default vector size for voyage-3.5-lite embeddings
    DEFAULT_VECTOR_SIZE = 1024

    def __init__(self, config_loader: Optional[ConfigLoader] = None):
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
                error_msg = ", ".join(result.errors) if result.errors else "Unknown error"
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
                message=f"Deleted collection '{collection_name}'"
                if result.success
                else f"Failed to delete: {result.errors}",
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
