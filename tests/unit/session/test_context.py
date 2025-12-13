"""Tests for SessionContext."""

import time
from pathlib import Path

from claude_indexer.session.context import SessionContext


class TestSessionContext:
    """Tests for SessionContext dataclass."""

    def test_create_context(self, tmp_path: Path) -> None:
        """Should create context with required fields."""
        context = SessionContext(
            session_id="test_123_abc",
            project_path=tmp_path,
            collection_name="test_collection",
        )

        assert context.session_id == "test_123_abc"
        assert context.project_path == tmp_path
        assert context.collection_name == "test_collection"
        assert context.config is None

    def test_create_context_with_string_path(self, tmp_path: Path) -> None:
        """Should convert string path to Path object."""
        context = SessionContext(
            session_id="test_123",
            project_path=str(tmp_path),  # Pass as string
            collection_name="test",
        )

        assert isinstance(context.project_path, Path)
        assert context.project_path == tmp_path

    def test_state_dir_property(self, tmp_path: Path) -> None:
        """Should return correct state directory path."""
        context = SessionContext(
            session_id="test",
            project_path=tmp_path,
            collection_name="test",
        )

        assert context.state_dir == tmp_path / ".claude-indexer"

    def test_lock_file_property(self, tmp_path: Path) -> None:
        """Should return correct lock file path."""
        context = SessionContext(
            session_id="test",
            project_path=tmp_path,
            collection_name="my_collection",
        )

        assert context.lock_file == tmp_path / ".claude-indexer" / "my_collection.lock"

    def test_session_file_property(self, tmp_path: Path) -> None:
        """Should return correct session file path."""
        context = SessionContext(
            session_id="test",
            project_path=tmp_path,
            collection_name="test",
        )

        assert context.session_file == tmp_path / ".claude-indexer" / "session.json"

    def test_touch_updates_last_activity(self, tmp_path: Path) -> None:
        """Should update last_activity timestamp on touch."""
        context = SessionContext(
            session_id="test",
            project_path=tmp_path,
            collection_name="test",
        )

        original_activity = context.last_activity
        time.sleep(0.01)  # Small delay
        context.touch()

        assert context.last_activity > original_activity

    def test_to_dict(self, tmp_path: Path) -> None:
        """Should serialize to dictionary correctly."""
        context = SessionContext(
            session_id="test_123",
            project_path=tmp_path,
            collection_name="my_collection",
            created_at=1000.0,
            last_activity=2000.0,
        )

        data = context.to_dict()

        assert data["session_id"] == "test_123"
        assert data["project_path"] == str(tmp_path)
        assert data["collection_name"] == "my_collection"
        assert data["created_at"] == 1000.0
        assert data["last_activity"] == 2000.0

    def test_from_dict(self, tmp_path: Path) -> None:
        """Should deserialize from dictionary correctly."""
        data = {
            "session_id": "test_456",
            "project_path": str(tmp_path),
            "collection_name": "restored_collection",
            "created_at": 3000.0,
            "last_activity": 4000.0,
        }

        context = SessionContext.from_dict(data)

        assert context.session_id == "test_456"
        assert context.project_path == tmp_path
        assert context.collection_name == "restored_collection"
        assert context.created_at == 3000.0
        assert context.last_activity == 4000.0

    def test_from_dict_with_config(self, tmp_path: Path) -> None:
        """Should accept optional config parameter."""
        from claude_indexer.config.models import IndexerConfig

        data = {
            "session_id": "test",
            "project_path": str(tmp_path),
            "collection_name": "test",
        }
        config = IndexerConfig()

        context = SessionContext.from_dict(data, config=config)

        assert context.config is config

    def test_round_trip_serialization(self, tmp_path: Path) -> None:
        """Should preserve data through serialize/deserialize cycle."""
        original = SessionContext(
            session_id="roundtrip_test",
            project_path=tmp_path,
            collection_name="roundtrip_collection",
            created_at=5000.0,
            last_activity=6000.0,
        )

        # Serialize and deserialize
        data = original.to_dict()
        restored = SessionContext.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.project_path == original.project_path
        assert restored.collection_name == original.collection_name
        assert restored.created_at == original.created_at
        assert restored.last_activity == original.last_activity

    def test_str_representation(self, tmp_path: Path) -> None:
        """Should have readable string representation."""
        context = SessionContext(
            session_id="abc123",
            project_path=tmp_path,
            collection_name="test_coll",
        )

        s = str(context)
        assert "abc123" in s
        assert "test_coll" in s
        assert tmp_path.name in s

    def test_repr_representation(self, tmp_path: Path) -> None:
        """Should have detailed repr for debugging."""
        context = SessionContext(
            session_id="xyz789",
            project_path=tmp_path,
            collection_name="debug_coll",
        )

        r = repr(context)
        assert "xyz789" in r
        assert "debug_coll" in r
        assert "created_at=" in r
        assert "last_activity=" in r

    def test_default_timestamps(self, tmp_path: Path) -> None:
        """Should set default timestamps to current time."""
        before = time.time()

        context = SessionContext(
            session_id="test",
            project_path=tmp_path,
            collection_name="test",
        )

        after = time.time()

        assert before <= context.created_at <= after
        assert before <= context.last_activity <= after

    def test_path_resolution(self) -> None:
        """Should resolve relative paths to absolute."""
        context = SessionContext(
            session_id="test",
            project_path=Path("."),  # Relative path
            collection_name="test",
        )

        # Path should be resolved to absolute
        assert context.project_path.is_absolute()
