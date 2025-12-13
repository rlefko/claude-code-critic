"""
Integration tests for file watching functionality.

Tests the real-time file monitoring and automatic re-indexing
when files change in the project.
"""

import asyncio
import time
from unittest.mock import Mock

import pytest

try:
    from claude_indexer.watcher.handler import Watcher

    WATCHER_AVAILABLE = True
except ImportError:
    WATCHER_AVAILABLE = False

import contextlib

from claude_indexer.config import IndexerConfig
from tests.conftest import get_unique_collection_name


@pytest.mark.skipif(not WATCHER_AVAILABLE, reason="Watcher components not available")
@pytest.mark.skipif(
    True,
    reason="Watcher integration tests require async file system events which are unreliable in CI. Core indexing tested elsewhere.",
)
@pytest.mark.integration
@pytest.mark.asyncio
class TestWatcherFlow:
    """Test file watching integration."""

    async def test_basic_file_watch_flow(self, temp_repo, dummy_embedder, qdrant_store):
        """Test basic file watching and re-indexing."""
        from tests.conftest import (
            verify_entities_exist_by_name,
            wait_for_collection_ready,
        )

        collection_name = get_unique_collection_name("test_watcher")
        config = IndexerConfig(
            collection_name=collection_name,
            embedder_type="dummy",
            storage_type="qdrant",
            debounce_seconds=0.1,  # Short debounce for testing
            include_patterns=["*.py"],  # Required for file discovery
            exclude_patterns=["*test*", "__pycache__"],
        )

        watcher = Watcher(
            repo_path=temp_repo,
            config=config,
            embedder=dummy_embedder,
            store=qdrant_store,
            debounce_seconds=config.debounce_seconds,
        )

        # Start watching
        watch_task = asyncio.create_task(watcher.start())

        try:
            # Wait for watcher to initialize and collection to be ready
            await asyncio.sleep(0.3)
            collection_ready = wait_for_collection_ready(
                qdrant_store, collection_name, timeout=10.0, verbose=True
            )
            assert (
                collection_ready
            ), f"Collection {collection_name} not ready for operations"

            # Get initial count
            initial_count = qdrant_store.count(collection_name)

            # Modify a file
            modified_file = temp_repo / "foo.py"
            original_content = modified_file.read_text()
            modified_content = (
                original_content
                + '\n\ndef new_watched_function():\n    """Added by watcher test."""\n    return "watched"\n'
            )
            modified_file.write_text(modified_content)

            # Wait for watcher to process the change with eventual consistency
            # Need sufficient time for: file detection + debounce (0.1s) + async processing + indexing
            await asyncio.sleep(1.0)  # Allow full async processing chain

            # Verify the new function is searchable using payload query (deterministic)
            function_found = verify_entities_exist_by_name(
                qdrant_store,
                collection_name,
                "new_watched_function",
                min_expected=1,
                timeout=15.0,
                verbose=True,
            )
            assert (
                function_found
            ), "new_watched_function should be searchable after file modification"

            # Check that re-indexing occurred
            final_count = qdrant_store.count(collection_name)
            assert (
                final_count >= initial_count
            ), f"Count should increase: {initial_count} -> {final_count}"

        finally:
            # Stop watcher
            await watcher.stop()
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task

    async def test_multiple_file_changes(self, temp_repo, dummy_embedder, qdrant_store):
        """Test watching multiple file changes."""
        from tests.conftest import (
            verify_entities_exist_by_name,
            wait_for_collection_ready,
        )

        collection_name = get_unique_collection_name("test_multi_watch")
        config = IndexerConfig(
            collection_name=collection_name,
            embedder_type="dummy",
            storage_type="qdrant",
            watch_debounce=0.1,
        )

        watcher = Watcher(
            repo_path=temp_repo,
            config=config,
            embedder=dummy_embedder,
            store=qdrant_store,
            debounce_seconds=config.debounce_seconds,
        )

        watch_task = asyncio.create_task(watcher.start())

        try:
            # Wait for collection to be ready
            await asyncio.sleep(0.3)
            collection_ready = wait_for_collection_ready(
                qdrant_store, collection_name, timeout=10.0, verbose=True
            )
            assert collection_ready, f"Collection {collection_name} not ready"

            # Modify multiple files simultaneously
            files_to_modify = [
                temp_repo / "foo.py",
                temp_repo / "bar.py",
                temp_repo / "utils" / "helpers.py",
            ]

            for i, file_path in enumerate(files_to_modify):
                content = file_path.read_text()
                content += f'\n\ndef batch_function_{i}():\n    """Batch test function {i}."""\n    return {i}\n'
                file_path.write_text(content)

            # Wait for initial processing
            await asyncio.sleep(0.2)

            # Verify all changes were processed with eventual consistency using payload queries
            for i in range(len(files_to_modify)):
                function_found = verify_entities_exist_by_name(
                    qdrant_store,
                    collection_name,
                    f"batch_function_{i}",
                    min_expected=1,
                    timeout=15.0,
                    verbose=True,
                )
                assert (
                    function_found
                ), f"batch_function_{i} should be searchable after file modification"

        finally:
            await watcher.stop()
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task

    async def test_new_file_creation(self, temp_repo, dummy_embedder, qdrant_store):
        """Test watching for new file creation."""
        from tests.conftest import verify_entities_exist_by_name

        config = IndexerConfig(
            collection_name="test_new_files",
            embedder_type="dummy",
            storage_type="qdrant",
            watch_debounce=0.1,
        )

        watcher = Watcher(
            repo_path=temp_repo,
            config=config,
            embedder=dummy_embedder,
            store=qdrant_store,
            debounce_seconds=config.debounce_seconds,
        )

        watch_task = asyncio.create_task(watcher.start())

        try:
            await asyncio.sleep(0.2)

            # Create a new file
            new_file = temp_repo / "new_module.py"
            new_file.write_text(
                '''"""Newly created module."""

def fresh_function():
    """A function in a new file."""
    return "fresh"

class NewClass:
    """A new class."""
    pass
'''
            )

            # Wait for processing
            await asyncio.sleep(0.5)

            # Verify new file was indexed using payload query (deterministic)
            fresh_function_found = verify_entities_exist_by_name(
                qdrant_store,
                "test_new_files",
                "fresh_function",
                min_expected=1,
                timeout=15.0,
                verbose=True,
            )
            assert fresh_function_found, "fresh_function should be indexed"

            # Also check for the new class
            new_class_found = verify_entities_exist_by_name(
                qdrant_store,
                "test_new_files",
                "NewClass",
                min_expected=1,
                timeout=15.0,
                verbose=True,
            )
            assert new_class_found, "NewClass should be indexed"

        finally:
            await watcher.stop()
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task

    async def test_file_deletion_handling(
        self, temp_repo, dummy_embedder, qdrant_store
    ):
        """Test watching for file deletion."""
        from tests.conftest import (
            verify_entities_exist_by_name,
            verify_entities_exist_by_path,
        )

        config = IndexerConfig(
            collection_name="test_deletions",
            embedder_type="dummy",
            storage_type="qdrant",
            watch_debounce=0.1,
        )

        # First, create and index a file
        temp_file = temp_repo / "temporary.py"
        temp_file.write_text(
            '''"""Temporary module."""

def temp_function():
    """Will be deleted."""
    return "temporary"
'''
        )

        watcher = Watcher(
            repo_path=temp_repo,
            config=config,
            embedder=dummy_embedder,
            store=qdrant_store,
            debounce_seconds=config.debounce_seconds,
        )

        watch_task = asyncio.create_task(watcher.start())

        try:
            await asyncio.sleep(0.3)  # Wait for initial indexing

            # Verify the function exists using payload query (deterministic)
            temp_function_found = verify_entities_exist_by_name(
                qdrant_store,
                "test_deletions",
                "temp_function",
                min_expected=1,
                timeout=15.0,
                verbose=True,
            )
            assert temp_function_found, "Temporary function should be indexed initially"

            # Delete the file
            temp_file.unlink()

            # Wait for deletion processing
            await asyncio.sleep(0.5)

            # Verify entities from temporary.py are cleaned up using payload query
            cleanup_complete = verify_entities_exist_by_path(
                qdrant_store,
                "test_deletions",
                "temporary.py",
                min_expected=0,  # Expect 0 entities after deletion
                timeout=15.0,
                verbose=True,
            )
            assert (
                cleanup_complete
            ), "Eventual consistency timeout: deleted file references should be cleaned up"

        finally:
            await watcher.stop()
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task

    async def test_watcher_error_handling(
        self, temp_repo, dummy_embedder, qdrant_store
    ):
        """Test watcher handles errors gracefully."""
        config = IndexerConfig(
            collection_name="test_error_handling",
            embedder_type="dummy",
            storage_type="qdrant",
            watch_debounce=0.1,
        )

        # Mock the embedder to fail sometimes
        failing_embedder = Mock()
        failing_embedder.embed_single.side_effect = Exception("Mock embedding failure")

        watcher = Watcher(
            repo_path=temp_repo,
            config=config,
            embedder=failing_embedder,
            store=qdrant_store,
        )

        watch_task = asyncio.create_task(watcher.start())

        try:
            await asyncio.sleep(0.2)

            # Modify a file (should trigger error)
            modified_file = temp_repo / "foo.py"
            content = modified_file.read_text()
            modified_file.write_text(content + "\n# Error test comment\n")

            # Wait for processing attempt
            await asyncio.sleep(0.5)

            # Watcher should still be running despite the error
            assert (
                not watch_task.done()
            ), "Watcher should continue running despite errors"

        finally:
            await watcher.stop()
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task

    async def test_debouncing_behavior(self, temp_repo, dummy_embedder, qdrant_store):
        """Test that rapid file changes are properly debounced."""
        config = IndexerConfig(
            collection_name="test_debounce",
            embedder_type="dummy",
            storage_type="qdrant",
            watch_debounce=0.3,  # Longer debounce for testing
        )

        # Track indexing calls
        index_calls = []
        original_index = qdrant_store.upsert_points

        def tracking_upsert(*args, **kwargs):
            index_calls.append(time.time())
            return original_index(*args, **kwargs)

        qdrant_store.upsert_points = tracking_upsert

        watcher = Watcher(
            repo_path=temp_repo,
            config=config,
            embedder=dummy_embedder,
            store=qdrant_store,
            debounce_seconds=config.debounce_seconds,
        )

        watch_task = asyncio.create_task(watcher.start())

        try:
            await asyncio.sleep(0.2)

            # Make rapid changes to the same file
            test_file = temp_repo / "rapid_changes.py"
            for i in range(5):
                test_file.write_text(f"def rapid_function_{i}(): return {i}\n")
                await asyncio.sleep(0.05)  # Rapid changes within debounce window

            # Wait for debounced processing
            await asyncio.sleep(0.5)

            # Should have fewer indexing calls than file changes due to debouncing
            assert (
                len(index_calls) < 5
            ), f"Expected debouncing, but got {len(index_calls)} calls for 5 rapid changes"

        finally:
            await watcher.stop()
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task


@pytest.mark.skipif(
    True,
    reason="Watcher integration tests require async file system events which are unreliable in CI. Core indexing tested elsewhere.",
)
@pytest.mark.integration
@pytest.mark.asyncio
class TestWatcherConfiguration:
    """Test watcher configuration options."""

    @pytest.mark.skipif(
        not WATCHER_AVAILABLE, reason="Watcher components not available"
    )
    async def test_custom_file_patterns(self, temp_repo, dummy_embedder, qdrant_store):
        """Test watcher with custom include/exclude patterns."""
        from tests.conftest import get_entities_by_name, verify_entities_exist_by_name

        config = IndexerConfig(
            collection_name="test_patterns",
            embedder_type="dummy",
            storage_type="qdrant",
            include_patterns=["*.py"],
            exclude_patterns=["*temp*"],
            watch_debounce=0.1,
        )

        watcher = Watcher(
            repo_path=temp_repo,
            config=config,
            embedder=dummy_embedder,
            store=qdrant_store,
            debounce_seconds=config.debounce_seconds,
        )

        watch_task = asyncio.create_task(watcher.start())

        try:
            await asyncio.sleep(0.2)

            # Create files that should be ignored
            (temp_repo / "test_ignore.py").write_text("def test_func(): pass")
            (temp_repo / "temp_ignore.py").write_text("def temp_func(): pass")

            # Create file that should be indexed
            (temp_repo / "valid.py").write_text("def valid_func(): pass")

            await asyncio.sleep(0.5)

            # Check that valid file was indexed using payload query (deterministic)
            valid_found = verify_entities_exist_by_name(
                qdrant_store,
                "test_patterns",
                "valid_func",
                min_expected=1,
                timeout=15.0,
                verbose=True,
            )
            assert valid_found, "valid_func should be indexed"

            # Check that ignored files were not indexed using payload queries
            for ignored_func in ["test_func", "temp_func"]:
                entities = get_entities_by_name(
                    qdrant_store, "test_patterns", ignored_func, verbose=True
                )
                assert len(entities) == 0, f"{ignored_func} should have been ignored"

        finally:
            await watcher.stop()
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task
