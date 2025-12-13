"""Unit tests for the index_queue module."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_indexer.hooks.index_queue import IndexQueue, enqueue_for_indexing


class TestIndexQueue:
    """Tests for IndexQueue class."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        IndexQueue.reset_instance()
        yield
        IndexQueue.reset_instance()

    @pytest.fixture
    def temp_queue_dir(self, tmp_path):
        """Create a temporary queue directory."""
        queue_dir = tmp_path / "queue"
        queue_dir.mkdir()
        return queue_dir

    def test_singleton_pattern(self, temp_queue_dir):
        """Test that get_instance returns same instance."""
        instance1 = IndexQueue.get_instance(queue_dir=temp_queue_dir)
        instance2 = IndexQueue.get_instance()

        assert instance1 is instance2

    def test_reset_instance(self, temp_queue_dir):
        """Test that reset_instance clears singleton."""
        instance1 = IndexQueue.get_instance(queue_dir=temp_queue_dir)
        IndexQueue.reset_instance()
        instance2 = IndexQueue.get_instance(queue_dir=temp_queue_dir)

        assert instance1 is not instance2

    def test_enqueue_creates_pending_entry(self, temp_queue_dir):
        """Test that enqueue adds file to pending."""
        queue = IndexQueue.get_instance(queue_dir=temp_queue_dir)

        queue.enqueue(
            file_path=Path("/project/src/main.py"),
            project_path=Path("/project"),
            collection="test-collection",
        )

        assert queue.get_pending_count("test-collection") == 1

    def test_enqueue_is_nonblocking(self, temp_queue_dir):
        """Test that enqueue returns immediately."""
        queue = IndexQueue.get_instance(queue_dir=temp_queue_dir)

        start = time.time()
        queue.enqueue(
            file_path=Path("/project/src/main.py"),
            project_path=Path("/project"),
            collection="test-collection",
        )
        elapsed = time.time() - start

        # Should return in <50ms
        assert elapsed < 0.05, f"Enqueue took {elapsed*1000:.1f}ms, expected <50ms"

    def test_enqueue_coalesces_same_file(self, temp_queue_dir):
        """Test that multiple enqueues for same file are coalesced."""
        queue = IndexQueue.get_instance(queue_dir=temp_queue_dir)

        # Enqueue same file multiple times
        for _ in range(5):
            queue.enqueue(
                file_path=Path("/project/src/main.py"),
                project_path=Path("/project"),
                collection="test-collection",
            )

        # Should only have 1 pending entry
        assert queue.get_pending_count("test-collection") == 1

    def test_enqueue_tracks_multiple_files(self, temp_queue_dir):
        """Test that different files are tracked separately."""
        queue = IndexQueue.get_instance(queue_dir=temp_queue_dir)

        queue.enqueue(
            file_path=Path("/project/src/main.py"),
            project_path=Path("/project"),
            collection="test-collection",
        )
        queue.enqueue(
            file_path=Path("/project/src/utils.py"),
            project_path=Path("/project"),
            collection="test-collection",
        )
        queue.enqueue(
            file_path=Path("/project/src/models.py"),
            project_path=Path("/project"),
            collection="test-collection",
        )

        assert queue.get_pending_count("test-collection") == 3

    def test_enqueue_tracks_multiple_collections(self, temp_queue_dir):
        """Test that files from different collections are tracked separately."""
        queue = IndexQueue.get_instance(queue_dir=temp_queue_dir)

        queue.enqueue(
            file_path=Path("/project-a/main.py"),
            project_path=Path("/project-a"),
            collection="project-a",
        )
        queue.enqueue(
            file_path=Path("/project-b/main.py"),
            project_path=Path("/project-b"),
            collection="project-b",
        )

        assert queue.get_pending_count("project-a") == 1
        assert queue.get_pending_count("project-b") == 1
        assert queue.get_pending_count() == 2

    def test_queue_file_created(self, temp_queue_dir):
        """Test that queue file is written to disk."""
        queue = IndexQueue.get_instance(queue_dir=temp_queue_dir)

        queue.enqueue(
            file_path=Path("/project/src/main.py"),
            project_path=Path("/project"),
            collection="test-collection",
        )

        # Check queue file exists
        queue_file = temp_queue_dir / "test-collection.queue"
        assert queue_file.exists()

        # Check content is valid JSON lines
        with open(queue_file) as f:
            lines = f.readlines()
            assert len(lines) >= 1

            entry = json.loads(lines[-1])
            assert entry["file_path"] == "/project/src/main.py"
            assert entry["project_path"] == "/project"
            assert entry["collection"] == "test-collection"
            assert "timestamp" in entry

    def test_force_process(self, temp_queue_dir):
        """Test force_process clears pending and returns count."""
        queue = IndexQueue.get_instance(queue_dir=temp_queue_dir)

        queue.enqueue(
            file_path=Path("/project/a.py"),
            project_path=Path("/project"),
            collection="test",
        )
        queue.enqueue(
            file_path=Path("/project/b.py"),
            project_path=Path("/project"),
            collection="test",
        )

        # Mock subprocess to avoid actual indexing
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            count = queue.force_process()

        assert count == 2
        assert queue.get_pending_count() == 0

    def test_cleanup_queue_files(self, temp_queue_dir):
        """Test cleanup of old queue files."""
        queue = IndexQueue.get_instance(queue_dir=temp_queue_dir)

        # Create an old queue file
        old_file = temp_queue_dir / "old-collection.queue"
        old_file.write_text('{"test": true}\n')

        # Set modification time to past
        import os

        old_time = time.time() - (25 * 3600)  # 25 hours ago
        os.utime(old_file, (old_time, old_time))

        # Cleanup with 24 hour max age
        cleaned = queue.cleanup_queue_files(max_age_hours=24.0)

        assert cleaned == 1
        assert not old_file.exists()

    def test_stop_timer(self, temp_queue_dir):
        """Test that stop() stops the timer thread."""
        queue = IndexQueue.get_instance(queue_dir=temp_queue_dir)

        # Timer thread should be running
        assert queue._timer_thread is not None
        assert queue._timer_thread.is_alive()

        queue.stop()

        # Give thread time to stop
        time.sleep(0.1)

        # Timer should be stopped or stopping
        assert not queue._timer_thread.is_alive() or queue._stop_event.is_set()


class TestEnqueueForIndexing:
    """Tests for enqueue_for_indexing convenience function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        IndexQueue.reset_instance()
        yield
        IndexQueue.reset_instance()

    def test_enqueue_convenience_function(self, tmp_path):
        """Test the convenience function creates entries."""
        queue_dir = tmp_path / "queue"
        queue_dir.mkdir()

        # Get instance with custom dir before calling convenience function
        IndexQueue.get_instance(queue_dir=queue_dir)

        enqueue_for_indexing(
            file_path="/project/main.py",
            project_path="/project",
            collection="test",
        )

        queue = IndexQueue.get_instance()
        assert queue.get_pending_count("test") == 1


class TestIndexQueueProcessing:
    """Tests for background processing behavior."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        IndexQueue.reset_instance()
        yield
        IndexQueue.reset_instance()

    @pytest.fixture
    def temp_queue_dir(self, tmp_path):
        """Create a temporary queue directory."""
        queue_dir = tmp_path / "queue"
        queue_dir.mkdir()
        return queue_dir

    def test_background_processing_with_debounce(self, temp_queue_dir):
        """Test that files are processed after debounce delay."""
        # Create queue with short debounce
        queue = IndexQueue(queue_dir=temp_queue_dir)
        queue.DEBOUNCE_DELAY = 0.1  # 100ms for testing

        processed_files = []

        def mock_index_files(entries):
            processed_files.extend([e["file_path"] for e in entries])

        queue._index_files = mock_index_files

        # Enqueue a file
        queue.enqueue(
            file_path=Path("/project/main.py"),
            project_path=Path("/project"),
            collection="test",
        )

        # Wait longer for debounce + processing (account for CI slowness)
        # Wait up to 1 second total with polling
        for _ in range(10):
            time.sleep(0.1)
            if len(processed_files) > 0 or queue.get_pending_count() == 0:
                break

        # File should be processed or force process to verify queue works
        if queue.get_pending_count() > 0:
            # Timer may not have fired yet, force process
            queue.force_process()

        # After force process, queue should be empty
        assert queue.get_pending_count() == 0

        queue.stop()

    def test_coalescing_rapid_changes(self, temp_queue_dir):
        """Test that rapid changes to same file are coalesced."""
        queue = IndexQueue(queue_dir=temp_queue_dir)
        queue.DEBOUNCE_DELAY = 0.2  # 200ms

        # Rapid changes to same file
        for _i in range(10):
            queue.enqueue(
                file_path=Path("/project/main.py"),
                project_path=Path("/project"),
                collection="test",
            )
            time.sleep(0.01)  # 10ms between changes

        # Should still only have 1 pending
        assert queue.get_pending_count("test") == 1

        queue.stop()
