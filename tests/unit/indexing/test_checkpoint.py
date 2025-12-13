"""Unit tests for IndexingCheckpoint."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from claude_indexer.indexing.checkpoint import IndexingCheckpoint


class TestIndexingCheckpoint:
    """Tests for IndexingCheckpoint class."""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path):
        """Create a temporary cache directory."""
        cache_dir = tmp_path / ".index_cache"
        cache_dir.mkdir(parents=True)
        return cache_dir

    @pytest.fixture
    def checkpoint(self, temp_cache_dir):
        """Create a checkpoint instance."""
        return IndexingCheckpoint(cache_dir=temp_cache_dir)

    def test_init_default(self, temp_cache_dir):
        """Test default initialization."""
        cp = IndexingCheckpoint(cache_dir=temp_cache_dir)
        assert cp.enabled is True
        assert cp._state is None
        assert cp._dirty is False

    def test_init_disabled(self, temp_cache_dir):
        """Test initialization with checkpointing disabled."""
        cp = IndexingCheckpoint(cache_dir=temp_cache_dir, enabled=False)
        assert cp.enabled is False

    def test_exists_no_checkpoint(self, checkpoint):
        """Test exists returns False when no checkpoint."""
        assert checkpoint.exists("test-collection") is False

    def test_exists_with_checkpoint(self, checkpoint, temp_cache_dir):
        """Test exists returns True with valid checkpoint."""
        # Create a checkpoint file
        now = datetime.now(UTC).isoformat()
        state = {
            "collection_name": "test-collection",
            "project_path": "/test/path",
            "total_files": 10,
            "processed_files": [],
            "pending_files": ["a.py"],
            "failed_files": [],
            "last_batch_index": 0,
            "entities_created": 0,
            "relations_created": 0,
            "chunks_created": 0,
            "started_at": now,
            "updated_at": now,
        }

        checkpoint_file = temp_cache_dir / "indexing_checkpoint_test-collection.json"
        with open(checkpoint_file, "w") as f:
            json.dump(state, f)

        assert checkpoint.exists("test-collection") is True

    def test_exists_stale_checkpoint(self, checkpoint, temp_cache_dir):
        """Test exists returns False for stale checkpoint."""
        # Create a checkpoint from 25 hours ago (stale)
        stale_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        state = {
            "collection_name": "test-collection",
            "project_path": "/test/path",
            "total_files": 10,
            "processed_files": [],
            "pending_files": ["a.py"],
            "failed_files": [],
            "last_batch_index": 0,
            "entities_created": 0,
            "relations_created": 0,
            "chunks_created": 0,
            "started_at": stale_time,
            "updated_at": stale_time,
        }

        checkpoint_file = temp_cache_dir / "indexing_checkpoint_test-collection.json"
        with open(checkpoint_file, "w") as f:
            json.dump(state, f)

        assert checkpoint.exists("test-collection") is False

    def test_create_checkpoint(self, checkpoint, tmp_path):
        """Test creating a new checkpoint."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        # Create some test files
        (project_path / "a.py").touch()
        (project_path / "b.py").touch()

        all_files = [project_path / "a.py", project_path / "b.py"]

        state = checkpoint.create(
            collection_name="test-collection",
            project_path=project_path,
            all_files=all_files,
        )

        assert state.collection_name == "test-collection"
        assert state.total_files == 2
        assert len(state.pending_files) == 2
        assert len(state.processed_files) == 0
        assert checkpoint._dirty is True

    def test_create_checkpoint_disabled(self, temp_cache_dir, tmp_path):
        """Test creating checkpoint when disabled."""
        cp = IndexingCheckpoint(cache_dir=temp_cache_dir, enabled=False)
        project_path = tmp_path / "project"
        project_path.mkdir()

        state = cp.create(
            collection_name="test",
            project_path=project_path,
            all_files=[project_path / "a.py"],
        )

        # Should still return a state but not be dirty
        assert state.collection_name == "test"
        assert cp._dirty is False

    def test_update_processed_file(self, checkpoint, tmp_path):
        """Test updating with processed file."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        (project_path / "a.py").touch()

        checkpoint.create(
            collection_name="test",
            project_path=project_path,
            all_files=[project_path / "a.py"],
        )

        checkpoint.update(processed_file=project_path / "a.py")

        state = checkpoint.get_state()
        assert "a.py" in state.processed_files
        assert "a.py" not in state.pending_files

    def test_update_failed_file(self, checkpoint, tmp_path):
        """Test updating with failed file."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        (project_path / "a.py").touch()

        checkpoint.create(
            collection_name="test",
            project_path=project_path,
            all_files=[project_path / "a.py"],
        )

        checkpoint.update(failed_file=project_path / "a.py")

        state = checkpoint.get_state()
        assert "a.py" in state.failed_files
        assert "a.py" not in state.pending_files

    def test_update_metrics(self, checkpoint, tmp_path):
        """Test updating metrics."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        checkpoint.create(
            collection_name="test",
            project_path=project_path,
            all_files=[],
        )

        checkpoint.update(
            batch_index=1,
            entities=10,
            relations=5,
            chunks=8,
        )

        state = checkpoint.get_state()
        assert state.last_batch_index == 1
        assert state.entities_created == 10
        assert state.relations_created == 5
        assert state.chunks_created == 8

    def test_update_batch(self, checkpoint, tmp_path):
        """Test batch update."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        (project_path / "a.py").touch()
        (project_path / "b.py").touch()
        (project_path / "c.py").touch()

        checkpoint.create(
            collection_name="test",
            project_path=project_path,
            all_files=[
                project_path / "a.py",
                project_path / "b.py",
                project_path / "c.py",
            ],
        )

        checkpoint.update_batch(
            processed_files=[project_path / "a.py", project_path / "b.py"],
            failed_files=[project_path / "c.py"],
            batch_index=0,
            entities=20,
            relations=10,
        )

        state = checkpoint.get_state()
        assert len(state.processed_files) == 2
        assert len(state.failed_files) == 1
        assert state.entities_created == 20

    def test_save_checkpoint(self, checkpoint, tmp_path):
        """Test saving checkpoint to disk."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        checkpoint.create(
            collection_name="test-collection",
            project_path=project_path,
            all_files=[],
        )
        checkpoint.save()

        # Check file exists
        checkpoint_file = (
            checkpoint.cache_dir / "indexing_checkpoint_test-collection.json"
        )
        assert checkpoint_file.exists()

        # Verify content
        with open(checkpoint_file) as f:
            data = json.load(f)
        assert data["collection_name"] == "test-collection"

    def test_load_checkpoint(self, checkpoint, temp_cache_dir):
        """Test loading checkpoint from disk."""
        now = datetime.now(UTC).isoformat()
        state = {
            "collection_name": "test-collection",
            "project_path": "/test/path",
            "total_files": 10,
            "processed_files": ["a.py"],
            "pending_files": ["b.py"],
            "failed_files": [],
            "last_batch_index": 1,
            "entities_created": 5,
            "relations_created": 3,
            "chunks_created": 4,
            "started_at": now,
            "updated_at": now,
        }

        checkpoint_file = temp_cache_dir / "indexing_checkpoint_test-collection.json"
        with open(checkpoint_file, "w") as f:
            json.dump(state, f)

        loaded = checkpoint.load("test-collection")

        assert loaded is not None
        assert loaded.collection_name == "test-collection"
        assert loaded.total_files == 10
        assert len(loaded.processed_files) == 1
        assert len(loaded.pending_files) == 1

    def test_load_returns_none_when_disabled(self, temp_cache_dir):
        """Test load returns None when disabled."""
        cp = IndexingCheckpoint(cache_dir=temp_cache_dir, enabled=False)
        assert cp.load("test") is None

    def test_clear_checkpoint(self, checkpoint, temp_cache_dir, tmp_path):
        """Test clearing checkpoint."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        checkpoint.create(
            collection_name="test-collection",
            project_path=project_path,
            all_files=[],
        )
        checkpoint.save()

        # Verify file exists
        checkpoint_file = temp_cache_dir / "indexing_checkpoint_test-collection.json"
        assert checkpoint_file.exists()

        checkpoint.clear("test-collection")

        assert not checkpoint_file.exists()
        assert checkpoint._state is None

    def test_get_pending_files(self, checkpoint, tmp_path):
        """Test getting pending files."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        (project_path / "a.py").touch()
        (project_path / "b.py").touch()

        checkpoint.create(
            collection_name="test",
            project_path=project_path,
            all_files=[project_path / "a.py", project_path / "b.py"],
        )

        # Mark one as processed
        checkpoint.update(processed_file=project_path / "a.py")

        pending = checkpoint.get_pending_files(project_path)

        assert len(pending) == 1
        assert pending[0].name == "b.py"

    def test_get_pending_files_skips_missing(self, checkpoint, tmp_path):
        """Test pending files skips files that no longer exist."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        (project_path / "a.py").touch()
        # b.py doesn't exist

        checkpoint.create(
            collection_name="test",
            project_path=project_path,
            all_files=[project_path / "a.py", project_path / "b.py"],
        )

        pending = checkpoint.get_pending_files(project_path)

        # Only a.py should be returned (b.py doesn't exist)
        assert len(pending) == 1
        assert pending[0].name == "a.py"

    def test_has_pending_property(self, checkpoint, tmp_path):
        """Test has_pending property."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        (project_path / "a.py").touch()

        checkpoint.create(
            collection_name="test",
            project_path=project_path,
            all_files=[project_path / "a.py"],
        )

        assert checkpoint.has_pending is True

        checkpoint.update(processed_file=project_path / "a.py")
        assert checkpoint.has_pending is False

    def test_progress_percent_property(self, checkpoint, tmp_path):
        """Test progress_percent property."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        for i in range(4):
            (project_path / f"file{i}.py").touch()

        checkpoint.create(
            collection_name="test",
            project_path=project_path,
            all_files=[project_path / f"file{i}.py" for i in range(4)],
        )

        assert checkpoint.progress_percent == 0.0

        # Process 2 files
        checkpoint.update(processed_file=project_path / "file0.py")
        checkpoint.update(processed_file=project_path / "file1.py")

        assert checkpoint.progress_percent == 50.0

    def test_atomic_save(self, checkpoint, tmp_path, temp_cache_dir):
        """Test atomic save using temp file + rename."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        checkpoint.create(
            collection_name="test-collection",
            project_path=project_path,
            all_files=[],
        )

        # Save should create file atomically
        checkpoint.save()

        # No temp files should remain
        temp_files = list(temp_cache_dir.glob("*.tmp"))
        assert len(temp_files) == 0

        # Checkpoint file should exist
        checkpoint_file = temp_cache_dir / "indexing_checkpoint_test-collection.json"
        assert checkpoint_file.exists()

    def test_collection_name_sanitization(self, checkpoint, temp_cache_dir):
        """Test collection names with special chars are sanitized."""
        # Collection name with slashes
        path = checkpoint._get_checkpoint_path("my/special/collection")
        assert "/" not in path.name or "\\" not in path.name
        assert "my_special_collection" in path.name
