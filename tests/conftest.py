"""
Shared fixtures for Claude Indexer test suite.

Provides test fixtures for:
- Temporary repository creation
- Qdrant client/store setup
- Mock embedder for fast testing
- Configuration management
"""

import json
import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from qdrant_client import QdrantClient


def pytest_addoption(parser):
    """Add custom command line option for watcher mode."""
    parser.addoption(
        "--watcher",
        action="store_true",
        default=False,
        help="Run tests using watcher mode instead of incremental indexing",
    )


# Import project components
try:
    from claude_indexer.config import IndexerConfig
    from claude_indexer.embeddings.openai import OpenAIEmbedder
    from claude_indexer.storage.qdrant import QdrantStore
except ImportError:
    # Graceful fallback for missing imports during test discovery
    IndexerConfig = None
    OpenAIEmbedder = None
    QdrantStore = None


# ---------------------------------------------------------------------------
# Temporary repository fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_repo(tmp_path_factory) -> Path:
    """Create a temporary repository with sample Python files for testing."""
    repo_path = tmp_path_factory.mktemp("sample_repo")

    # Create sample Python files
    (repo_path / "foo.py").write_text(
        '''"""Sample module with functions."""

def add(x, y):
    """Return sum of two numbers."""
    return x + y

class Calculator:
    """Simple calculator class."""

    def multiply(self, a, b):
        """Multiply two numbers."""
        return a * b
'''
    )

    (repo_path / "bar.py").write_text(
        '''"""Module that imports and uses foo."""
from foo import add, Calculator

def main():
    """Main function that uses imported components."""
    result = add(1, 2)
    calc = Calculator()
    product = calc.multiply(3, 4)
    print(f"Results: {result}, {product}")

if __name__ == "__main__":
    main()
'''
    )

    # Create a subdirectory with more code
    subdir = repo_path / "utils"
    subdir.mkdir()
    (subdir / "__init__.py").write_text("")
    (subdir / "helpers.py").write_text(
        '''"""Helper utilities."""

def format_output(value):
    """Format value for display."""
    return f"Value: {value}"

LOG_LEVEL = "INFO"
'''
    )

    # Create a test file (will be excluded by default)
    test_dir = repo_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text(
        '''"""Tests for foo module."""
import pytest
from foo import add

def test_add():
    assert add(2, 3) == 5
'''
    )

    # Create .claude-indexer/config.json for ProjectConfigManager
    # This prevents FileNotFoundError in watcher tests
    config_dir = repo_path / ".claude-indexer"
    config_dir.mkdir()
    config_json = {
        "version": "2.6",
        "project": {
            "name": "test-project",
            "collection": "test-collection",
            "description": "Test project for integration tests",
        },
        "indexing": {
            "file_patterns": {
                "include": ["*.py"],
                "exclude": ["__pycache__/", ".git/", "*test*"],
            }
        },
        "watcher": {"enabled": True, "debounce_seconds": 0.1},
    }
    (config_dir / "config.json").write_text(json.dumps(config_json, indent=2))

    return repo_path


@pytest.fixture()
def empty_repo(tmp_path_factory) -> Path:
    """Create an empty temporary repository."""
    return tmp_path_factory.mktemp("empty_repo")


# ---------------------------------------------------------------------------
# Test collection utilities
# ---------------------------------------------------------------------------


def get_test_collection_name(base_name: str = "test_collection") -> str:
    """Generate a unique test collection name with timestamp.

    DEPRECATED: Use get_unique_collection_name() for guaranteed uniqueness.
    This function uses second-precision timestamps which can cause collisions.
    """
    import time

    timestamp = int(time.time())
    return f"{base_name}_{timestamp}"


def get_unique_collection_name(prefix: str = "test") -> str:
    """Generate guaranteed unique collection name using UUID4.

    This should be used instead of get_test_collection_name() to avoid
    collection name collisions in rapid test execution scenarios.
    """
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def is_production_collection(collection_name: str) -> bool:
    """Check if a collection name is a production collection that should never be deleted."""
    PRODUCTION_COLLECTIONS = {
        "claude-memory-test",
        "memory-project",
        "general",
        "watcher-test",  # Add watcher-test as it's used for debugging
        "parser-test",  # Used by integration tests - don't cleanup
    }
    return collection_name in PRODUCTION_COLLECTIONS


# ---------------------------------------------------------------------------
# Qdrant test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qdrant_client() -> Iterator[QdrantClient]:
    """Create a Qdrant client for testing with session scope."""
    # Load config to get API key from settings.txt
    from claude_indexer.config import load_config

    config = load_config()

    # Use authentication if available
    if config.qdrant_api_key and config.qdrant_api_key != "default-key":
        client = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)
    else:
        # Fall back to unauthenticated for local testing
        client = QdrantClient("localhost", port=6333)

    # Verify Qdrant is available without pre-creating collections.
    # Collections are created by CoreIndexer/QdrantStore via production path
    # with proper named vector configuration (dense + bm25 sparse vectors).
    # Pre-creating with unnamed vectors causes search() to fail since it
    # expects named "dense" vector: query_vector=("dense", query_vector)
    try:
        client.get_collections()
    except Exception as e:
        pytest.skip(f"Qdrant not available: {e}")

    yield client

    # Cleanup: Remove ONLY temporary test collections after test session
    try:
        collections = client.get_collections().collections
        # Only cleanup collections that are clearly temporary test collections
        test_collections = [
            c.name
            for c in collections
            if (
                c.name.startswith("test_")  # test_ prefix
                or c.name.endswith("_test")  # _test suffix
                or "integration" in c.name.lower()  # integration tests
                or "temp" in c.name.lower()  # temporary collections
                or any(
                    char.isdigit() for char in c.name
                )  # has numbers (likely timestamps)
            )
            and not is_production_collection(
                c.name
            )  # NEVER delete production collections
        ]
        for collection_name in test_collections:
            try:
                client.delete_collection(collection_name)
                print(f"Cleaned up test collection: {collection_name}")
            except Exception as e:
                print(f"Warning: Failed to cleanup collection {collection_name}: {e}")
    except Exception as e:
        print(f"Warning: Failed to cleanup test collections: {e}")


@pytest.fixture()
def qdrant_store(qdrant_client) -> "QdrantStore":
    """Create a QdrantStore instance for testing."""
    if QdrantStore is None:
        pytest.skip("QdrantStore not available")

    # Load config to get API credentials
    from claude_indexer.config import load_config

    config = load_config()

    store = QdrantStore(
        url=config.qdrant_url,
        api_key=(
            config.qdrant_api_key if config.qdrant_api_key != "default-key" else None
        ),
    )

    # Clean up any existing test data
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        Filter(must=[FieldCondition(key="test", match=MatchValue(value=True))])
        # Note: collection_name should be passed from fixture if needed
        # For now, skip cleanup since we use timestamped collections
        pass
    except Exception as e:
        # Log cleanup failures instead of silently ignoring them
        import warnings

        warnings.warn(f"QdrantStore cleanup failed: {e}", stacklevel=2)

    return store


@pytest.fixture()
def ensure_test_collection(qdrant_store):
    """
    Helper fixture to create collections with proper named vector configuration.

    This ensures collections are created via the production path with
    named vectors ("dense" + "bm25" sparse), matching what CoreIndexer expects.
    Use this when you need to explicitly create a collection for testing
    without going through CoreIndexer.

    Usage:
        def test_example(ensure_test_collection, qdrant_store):
            collection_name = ensure_test_collection("my_test_collection")
            # Collection now exists with proper configuration
    """
    created_collections = []

    def _ensure_collection(collection_name: str) -> str:
        """Ensure collection exists with proper named vector configuration."""
        # Delete existing collection to ensure clean state
        if qdrant_store.collection_exists(collection_name):
            qdrant_store.delete_collection(collection_name)

        # Create with sparse vector support (production path)
        vector_size = 1536  # Match dummy_embedder dimension
        qdrant_store.create_collection_with_sparse_vectors(
            collection_name=collection_name,
            dense_vector_size=vector_size,
            distance_metric="cosine",
        )
        created_collections.append(collection_name)
        return collection_name

    yield _ensure_collection

    # Cleanup created collections
    for name in created_collections:
        try:
            if qdrant_store.collection_exists(name):
                qdrant_store.delete_collection(name)
        except Exception:
            pass  # Best effort cleanup


@pytest.fixture()
def isolated_config(tmp_path):
    """
    Create IndexerConfig with isolated state directory for test isolation.

    Each test gets its own state directory via pytest's tmp_path fixture,
    preventing state file contamination between tests.

    Usage:
        def test_example(isolated_config, temp_repo, dummy_embedder, qdrant_store):
            collection_name = get_unique_collection_name("test_example")
            config = isolated_config(collection_name)
            indexer = CoreIndexer(config=config, embedder=dummy_embedder,
                                  vector_store=qdrant_store, project_path=temp_repo)
    """
    from claude_indexer.config import IndexerConfig, load_config

    # Load base config for API credentials
    base_config = load_config()

    def _create_config(collection_name: str, **kwargs) -> IndexerConfig:
        return IndexerConfig(
            collection_name=collection_name,
            embedder_type="dummy",
            storage_type="qdrant",
            state_directory=tmp_path / "indexer_state",
            openai_api_key=base_config.openai_api_key,
            qdrant_api_key=base_config.qdrant_api_key,
            qdrant_url=base_config.qdrant_url,
            **kwargs,
        )

    return _create_config


# ---------------------------------------------------------------------------
# Mock embedder fixtures
# ---------------------------------------------------------------------------


class DummyEmbedder:
    """Fast, deterministic embedder for testing."""

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def embed_text(self, text: str):
        """Generate embedding for single text - interface compatibility."""
        from claude_indexer.embeddings.base import EmbeddingResult

        # Create deterministic but unique embedding
        seed = hash(text) % 10000
        np.random.seed(seed)
        embedding = np.random.rand(self.dimension).astype(np.float32).tolist()

        return EmbeddingResult(
            text=text,
            embedding=embedding,
            model="dummy",
            token_count=len(text.split()),
            processing_time=0.001,
        )

    def embed_batch(self, texts: list[str], item_type: str = "general"):
        """Generate embeddings for multiple texts.

        Args:
            texts: List of text strings to embed
            item_type: Type of items being embedded (unused by dummy embedder)
        """
        return [self.embed_text(text) for text in texts]

    def get_model_info(self):
        """Get model information."""
        return {"model": "dummy", "dimension": self.dimension, "max_tokens": 8192}

    def get_max_tokens(self):
        """Get maximum token limit."""
        return 8192

    def embed_single(self, text: str) -> np.ndarray:
        """Legacy method for backward compatibility."""
        result = self.embed_text(text)
        return np.array(result.embedding, dtype=np.float32)

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        """Generate deterministic embeddings based on text hash."""
        embeddings = []
        for _i, text in enumerate(texts):
            # Create deterministic but unique embeddings
            seed = hash(text) % 10000
            np.random.seed(seed)
            embedding = np.random.rand(self.dimension).astype(np.float32)
            embeddings.append(embedding)
        return embeddings


@pytest.fixture()
def dummy_embedder() -> DummyEmbedder:
    """Provide a fast, deterministic embedder for tests."""
    return DummyEmbedder()


@pytest.fixture()
def mock_openai_embedder(monkeypatch) -> DummyEmbedder:
    """Mock OpenAI embedder with dummy implementation."""
    dummy = DummyEmbedder()

    if OpenAIEmbedder is not None:
        monkeypatch.setattr(OpenAIEmbedder, "embed_text", dummy.embed_text)
        monkeypatch.setattr(OpenAIEmbedder, "embed_batch", dummy.embed_batch)

    return dummy


# ---------------------------------------------------------------------------
# Configuration fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_config(tmp_path) -> "IndexerConfig":
    """Create test configuration with temporary paths."""
    if IndexerConfig is None:
        pytest.skip("IndexerConfig class not available")

    # Load real config from settings.txt and create test settings file
    from claude_indexer.config import load_config

    real_config = load_config()

    settings_file = tmp_path / "test_settings.txt"
    settings_content = f"""
openai_api_key={real_config.openai_api_key}
qdrant_api_key={real_config.qdrant_api_key}
qdrant_url={real_config.qdrant_url}
"""
    settings_file.write_text(settings_content.strip())

    # Create temporary state directory for test isolation
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)

    config = load_config(settings_file)
    config.state_directory = state_dir  # Override state directory for tests

    # Override include patterns for tests - only include source files, not config files
    # Tests primarily create .py files, avoid including *.json which matches cache files
    config.include_patterns = ["*.py", "*.js", "*.ts", "*.tsx"]

    # Ensure test cache directories are excluded
    if ".index_cache/" not in config.exclude_patterns:
        config.exclude_patterns = list(config.exclude_patterns) + [".index_cache/"]

    return config


# ---------------------------------------------------------------------------
# File system fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_python_file(tmp_path) -> Path:
    """Create a single sample Python file for testing."""
    py_file = tmp_path / "sample.py"
    py_file.write_text(
        '''"""Sample Python file for testing."""

class SampleClass:
    """A sample class."""

    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        """Return a greeting."""
        return f"Hello, {self.name}!"

def utility_function(data: list) -> int:
    """Process data and return count."""
    return len([x for x in data if x])

# Module-level variable
DEFAULT_NAME = "World"
'''
    )
    return py_file


@pytest.fixture()
def sample_files_with_changes(tmp_path) -> tuple[Path, dict]:
    """Create sample files and return info about planned changes."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Original file
    original = repo / "original.py"
    original.write_text('def old_func(): return "old"')

    # File to be modified
    modified = repo / "modified.py"
    modified.write_text("def func(): return 1")

    # File to be deleted
    deleted = repo / "deleted.py"
    deleted.write_text('def func(): return "delete me"')

    changes = {
        "modify": (modified, "def func(): return 2"),  # Changed return value
        "delete": deleted,
        "add": (repo / "new.py", 'def new_func(): return "new"'),
    }

    return repo, changes


# ---------------------------------------------------------------------------
# Async fixtures for file watching tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def event_loop():
    """Create an event loop for async tests."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Marker decorators
# ---------------------------------------------------------------------------


def requires_qdrant(func):
    """Decorator to skip tests if Qdrant is not available."""
    return pytest.mark.skipif(not _qdrant_available(), reason="Qdrant not available")(
        func
    )


def requires_openai(func):
    """Decorator to skip tests if OpenAI API key is not available."""
    return pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available"
    )(func)


def _qdrant_available() -> bool:
    """Check if Qdrant is available."""
    try:
        # Load config to get API key from settings.txt
        from claude_indexer.config import load_config

        config = load_config()

        # Use authentication if available
        if config.qdrant_api_key and config.qdrant_api_key != "default-key":
            client = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)
        else:
            # Fall back to unauthenticated for local testing
            client = QdrantClient("localhost", port=6333)

        client.get_collections()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Additional cleanup fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(
    autouse=False, scope="function"
)  # DISABLED - was deleting production collections
def cleanup_test_collections_on_failure():
    """Cleanup test collections after each test function to prevent accumulation."""
    yield  # Run the test

    # Only perform cleanup if Qdrant is available
    if not _qdrant_available():
        return

    # Cleanup any collections created during this test that match test patterns
    try:
        from claude_indexer.config import load_config

        config = load_config()

        if config.qdrant_api_key and config.qdrant_api_key != "default-key":
            client = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)
        else:
            client = QdrantClient("localhost", port=6333)

        collections = client.get_collections().collections
        # Only cleanup collections that look like temporary test collections
        # PRODUCTION SAFEGUARD: Use centralized production collection check
        temp_test_collections = [
            c.name
            for c in collections
            if (
                not is_production_collection(c.name)
                and (
                    "test" in c.name.lower()
                    and (
                        any(
                            char.isdigit() for char in c.name
                        )  # has numbers (likely timestamps)
                        or c.name.startswith("test_")  # any test collection
                        or c.name.endswith("_test")  # reverse pattern
                        or "integration" in c.name.lower()  # integration tests
                        or "delete" in c.name.lower()
                    )
                )
            )  # deletion tests
        ]

        for collection_name in temp_test_collections:
            try:
                client.delete_collection(collection_name)
            except Exception as e:
                # Log but don't fail - cleanup errors shouldn't break tests
                print(f"Warning: Failed to cleanup collection {collection_name}: {e}")

    except Exception as e:
        # Log cleanup failures so they're visible in test output
        import warnings

        warnings.warn(f"Test collection cleanup failed: {e}", stacklevel=2)


# ---------------------------------------------------------------------------
# Utility functions for tests
# ---------------------------------------------------------------------------


def assert_valid_embedding(embedding: np.ndarray, expected_dim: int = 1536):
    """Assert that an embedding has the correct shape and type."""
    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (expected_dim,)
    assert embedding.dtype == np.float32
    assert not np.isnan(embedding).any()
    assert not np.isinf(embedding).any()


def count_python_files(path: Path) -> int:
    """Count Python files in a directory recursively."""
    return len(list(path.rglob("*.py")))


def wait_for_eventual_consistency(
    search_func,
    expected_count: int = 0,
    timeout: float = 30.0,  # Increased from 15.0 for CI network latency
    initial_delay: float = 0.5,
    max_delay: float = 3.0,
    backoff_multiplier: float = 1.2,
    verbose: bool = False,
) -> bool:
    """
    Wait for Qdrant eventual consistency by retrying searches until entities are properly deleted.

    Args:
        search_func: Function that returns search results (should return list/count)
        expected_count: Expected number of results after consistency (default: 0 for deletions)
        timeout: Maximum time to wait in seconds
        initial_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        backoff_multiplier: Multiplier for exponential backoff
        verbose: Print debug information

    Returns:
        True if eventual consistency achieved, False if timeout
    """
    import time

    start_time = time.time()
    delay = initial_delay
    attempt = 0
    last_results = None

    # Start with a small initial delay to allow Qdrant to process the deletion
    time.sleep(0.2)

    while time.time() - start_time < timeout:
        attempt += 1

        try:
            results = search_func()

            # Handle different return types
            if hasattr(results, "__len__"):
                actual_count = len(results)
            elif isinstance(results, int | float):
                actual_count = int(results)
            else:
                actual_count = 1 if results else 0

            if verbose:
                print(
                    f"Attempt {attempt}: Expected {expected_count}, got {actual_count}"
                )
                if hasattr(results, "__len__") and len(results) > 0 and verbose:
                    # Show details of what's still being found
                    for i, result in enumerate(results[:3]):  # Show first 3 results
                        if hasattr(result, "payload"):
                            name = result.payload.get("name", "Unknown")
                            file_path = (
                                get_file_path_from_payload(result.payload) or "Unknown"
                            )
                            print(f"  Still found #{i + 1}: {name} in {file_path}")
                        else:
                            print(f"  Still found #{i + 1}: {result}")

            if actual_count == expected_count:
                if verbose:
                    print(
                        f"Eventual consistency achieved after {time.time() - start_time:.2f}s"
                    )
                return True

            # If count hasn't changed for several attempts, try a longer delay
            if last_results is not None and actual_count == last_results:
                delay = min(delay * 1.5, max_delay)

            last_results = actual_count

        except Exception as e:
            # Always log search errors - they indicate real problems
            print(f"Search attempt {attempt} failed: {e}")
            # Continue retrying on search errors

        # Wait before next attempt with exponential backoff
        time.sleep(delay)
        delay = min(delay * backoff_multiplier, max_delay)

    if verbose:
        print(f"Timeout reached after {timeout}s, last count: {last_results}")
    return False


def wait_for_collection_ready(
    qdrant_store,
    collection_name: str,
    timeout: float = 15.0,
    initial_delay: float = 0.2,
    max_delay: float = 2.0,
    verbose: bool = False,
) -> bool:
    """
    Wait for a Qdrant collection to exist and be ready for operations.

    Args:
        qdrant_store: QdrantStore instance
        collection_name: Name of collection to wait for
        timeout: Maximum time to wait in seconds
        initial_delay: Initial delay between checks
        max_delay: Maximum delay between checks
        verbose: Print debug information

    Returns:
        True if collection is ready, False if timeout
    """
    import time

    start_time = time.time()
    delay = initial_delay
    attempt = 0

    if verbose:
        print(f"Waiting for collection '{collection_name}' to be ready...")

    while time.time() - start_time < timeout:
        attempt += 1

        try:
            # Check if collection exists
            if qdrant_store.collection_exists(collection_name):
                # Try a simple count operation to verify it's ready
                count = qdrant_store.count(collection_name)
                if verbose:
                    print(f"Collection '{collection_name}' ready with {count} points")
                return True
            elif verbose:
                print(f"Attempt {attempt}: Collection '{collection_name}' not found")

        except Exception as e:
            # Always log errors - they indicate real problems
            print(f"Attempt {attempt}: Collection check failed: {e}")

        time.sleep(delay)
        delay = min(delay * 1.5, max_delay)

    # Always log timeout - this is important for debugging
    print(f"Timeout: Collection '{collection_name}' not ready after {timeout}s")
    return False


def get_file_path_from_payload(payload: dict) -> str:
    """
    Extract file_path from a Qdrant payload, handling both legacy and current structures.

    Current structure: file_path is nested inside metadata dict.
    Legacy structure: file_path was at top level (for backward compatibility).
    File entities: entity_name may contain the file path.

    Args:
        payload: Qdrant payload dict

    Returns:
        file_path string or empty string if not found
    """
    # Try top-level first (legacy structure)
    file_path = payload.get("file_path", "")
    if file_path:
        return file_path

    # Try nested in metadata (current structure)
    metadata = payload.get("metadata", {})
    if isinstance(metadata, dict):
        file_path = metadata.get("file_path", "")
        if file_path:
            return file_path

    # For file entities, entity_name may contain the path
    entity_name = payload.get("entity_name", "")
    if entity_name and "/" in entity_name and entity_name.endswith(".py"):
        return entity_name

    return ""


def verify_entity_searchable(
    qdrant_store,
    dummy_embedder,
    collection_name: str,
    entity_name: str,
    timeout: float = 10.0,
    verbose: bool = False,
    expected_count: int = 1,
) -> bool:
    """
    Verify that a specific entity is indexed and searchable.

    Args:
        qdrant_store: QdrantStore instance
        dummy_embedder: Embedder for search queries
        collection_name: Collection to search in
        entity_name: Name of entity to search for
        timeout: Maximum time to wait
        verbose: Print debug information
        expected_count: Expected number of entities to find (default: 1)

    Returns:
        True if entity is found, False if timeout
    """

    def search_for_entity():
        search_embedding = dummy_embedder.embed_single(entity_name)
        # Increase top_k to handle cases where target entity might not be in top 10
        # due to DummyEmbedder's deterministic but not perfect scoring
        hits = qdrant_store.search(collection_name, search_embedding, top_k=50)
        if verbose:
            print(
                f"DEBUG: Searching for '{entity_name}' in collection '{collection_name}'"
            )
            print(f"DEBUG: Found {len(hits)} total hits")
            for i, hit in enumerate(hits[:10]):
                entity_name_field = hit.payload.get("entity_name", "NO_NAME")
                name_field = hit.payload.get("name", "NO_NAME")
                print(
                    f"DEBUG: Hit {i}: entity_name='{entity_name_field}', "
                    f"name='{name_field}', score={hit.score}"
                )
                if entity_name in str(hit.payload):
                    print(
                        f"DEBUG: Hit {i} contains '{entity_name}' in payload: {hit.payload}"
                    )
        # Enhanced matching logic for unique entity name matches only
        # Focus on entities that have the search term in their actual name
        # This provides more precise matching for test expectations
        unique_entity_names = set()
        matching_hits = []

        for hit in hits:
            chunk_type = hit.payload.get("chunk_type", "")
            entity_name_field = hit.payload.get("entity_name", "")

            # Skip relations and file paths
            if chunk_type == "relation" or entity_name_field.startswith("/"):
                continue

            # Only match if search term is in the entity name (not just content)
            if (
                entity_name in entity_name_field
                and entity_name_field not in unique_entity_names
            ):
                unique_entity_names.add(entity_name_field)
                matching_hits.append(hit)
                if verbose:
                    print(
                        f"DEBUG: Unique entity match - "
                        f"entity_name='{entity_name_field}', chunk_type='{chunk_type}'"
                    )

        if verbose:
            print(
                f"DEBUG: Found {len(matching_hits)} unique entity matches for '{entity_name}'"
            )
        return matching_hits

    return wait_for_eventual_consistency(
        search_for_entity,
        expected_count=expected_count,
        timeout=timeout,
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# Payload-based query helpers (deterministic, no embedding dependency)
# ---------------------------------------------------------------------------


def get_entities_by_file_path(
    qdrant_store, collection_name: str, file_path_pattern: str, verbose: bool = False
) -> list:
    """
    Get entities from collection matching a file path pattern using payload filter.

    This bypasses the embedding system entirely, providing deterministic results
    regardless of what embedder is used. Use this for testing entity existence.

    Args:
        qdrant_store: QdrantStore instance
        collection_name: Name of collection to query
        file_path_pattern: Substring to match in file_path field
        verbose: Print debug information

    Returns:
        List of Qdrant points matching the pattern
    """
    from qdrant_client.models import FieldCondition, Filter, MatchText

    try:
        # Query using payload filter - try both top-level and nested file_path
        results, _ = qdrant_store.client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                should=[
                    FieldCondition(
                        key="file_path", match=MatchText(text=file_path_pattern)
                    ),
                    FieldCondition(
                        key="metadata.file_path",
                        match=MatchText(text=file_path_pattern),
                    ),
                ]
            ),
            limit=100,
            with_payload=True,
        )

        if verbose:
            print(
                f"DEBUG: get_entities_by_file_path('{file_path_pattern}') "
                f"found {len(results)} entities"
            )
            for i, point in enumerate(results[:5]):
                entity_name = point.payload.get("entity_name", "N/A")
                file_path = get_file_path_from_payload(point.payload)
                print(f"  {i}: entity_name='{entity_name}', file_path='{file_path}'")

        return results

    except Exception as e:
        if verbose:
            print(f"DEBUG: get_entities_by_file_path failed: {e}")
        return []


def get_entities_by_name(
    qdrant_store, collection_name: str, entity_name: str, verbose: bool = False
) -> list:
    """
    Get entities from collection matching an entity name using payload filter.

    This bypasses the embedding system entirely, providing deterministic results
    regardless of what embedder is used. Use this for testing entity existence.

    Args:
        qdrant_store: QdrantStore instance
        collection_name: Name of collection to query
        entity_name: Substring to match in entity_name or name field
        verbose: Print debug information

    Returns:
        List of Qdrant points matching the name
    """
    from qdrant_client.models import FieldCondition, Filter, MatchText

    try:
        # Query using payload filter - try both entity_name and name fields
        results, _ = qdrant_store.client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                should=[
                    FieldCondition(
                        key="entity_name", match=MatchText(text=entity_name)
                    ),
                    FieldCondition(key="name", match=MatchText(text=entity_name)),
                ]
            ),
            limit=100,
            with_payload=True,
        )

        if verbose:
            print(
                f"DEBUG: get_entities_by_name('{entity_name}') "
                f"found {len(results)} entities"
            )
            for i, point in enumerate(results[:5]):
                name_field = point.payload.get("entity_name", "N/A")
                chunk_type = point.payload.get("chunk_type", "N/A")
                print(f"  {i}: entity_name='{name_field}', chunk_type='{chunk_type}'")

        return results

    except Exception as e:
        if verbose:
            print(f"DEBUG: get_entities_by_name failed: {e}")
        return []


def verify_entities_exist_by_path(
    qdrant_store,
    collection_name: str,
    path_pattern: str,
    min_expected: int = 1,
    timeout: float = 15.0,
    verbose: bool = False,
) -> bool:
    """
    Verify that entities from a file path exist in the collection.

    Uses payload-based queries for deterministic verification without
    relying on embedding similarity.

    Args:
        qdrant_store: QdrantStore instance
        collection_name: Name of collection to query
        path_pattern: Substring to match in file_path
        min_expected: Minimum number of entities expected (default: 1).
                      Use 0 to verify entities are deleted.
        timeout: Maximum time to wait for eventual consistency
        verbose: Print debug information

    Returns:
        True if condition is met, False if timeout
    """
    import time

    start_time = time.time()
    delay = 0.5

    while time.time() - start_time < timeout:
        results = get_entities_by_file_path(
            qdrant_store, collection_name, path_pattern, verbose=False
        )
        actual_count = len(results)

        if verbose:
            print(
                f"verify_entities_exist_by_path: min_expected={min_expected}, "
                f"actual={actual_count}"
            )

        if min_expected > 0:
            # For existence check: at least min_expected entities
            if actual_count >= min_expected:
                if verbose:
                    print(
                        f"Found {actual_count} entities (>= {min_expected}) "
                        f"after {time.time() - start_time:.2f}s"
                    )
                return True
        else:
            # For deletion check: exactly 0 entities
            if actual_count == 0:
                if verbose:
                    print(f"Verified 0 entities after {time.time() - start_time:.2f}s")
                return True

        time.sleep(delay)
        delay = min(delay * 1.2, 3.0)

    if verbose:
        print(
            f"Timeout: expected {'>=' if min_expected > 0 else '=='} "
            f"{min_expected}, got {actual_count}"
        )
    return False


def verify_entities_exist_by_name(
    qdrant_store,
    collection_name: str,
    entity_name: str,
    min_expected: int = 1,
    timeout: float = 15.0,
    verbose: bool = False,
) -> bool:
    """
    Verify that entities with a given name exist in the collection.

    Uses payload-based queries for deterministic verification without
    relying on embedding similarity. This is a drop-in replacement for
    verify_entity_searchable that doesn't depend on DummyEmbedder.

    Args:
        qdrant_store: QdrantStore instance
        collection_name: Name of collection to query
        entity_name: Substring to match in entity_name or name field
        min_expected: Minimum number of entities expected (default: 1).
                      Use 0 to verify entities are deleted.
        timeout: Maximum time to wait for eventual consistency
        verbose: Print debug information

    Returns:
        True if condition is met, False if timeout
    """
    import time

    start_time = time.time()
    delay = 0.5

    while time.time() - start_time < timeout:
        results = get_entities_by_name(
            qdrant_store, collection_name, entity_name, verbose=False
        )
        actual_count = len(results)

        if verbose:
            print(
                f"verify_entities_exist_by_name('{entity_name}'): "
                f"min_expected={min_expected}, actual={actual_count}"
            )

        if min_expected > 0:
            # For existence check: at least min_expected entities
            if actual_count >= min_expected:
                if verbose:
                    print(
                        f"Found {actual_count} entities (>= {min_expected}) "
                        f"after {time.time() - start_time:.2f}s"
                    )
                return True
        else:
            # For deletion check: exactly 0 entities
            if actual_count == 0:
                if verbose:
                    print(f"Verified 0 entities after {time.time() - start_time:.2f}s")
                return True

        time.sleep(delay)
        delay = min(delay * 1.2, 3.0)

    if verbose:
        print(
            f"Timeout: expected {'>=' if min_expected > 0 else '=='} "
            f"{min_expected}, got {actual_count}"
        )
    return False
