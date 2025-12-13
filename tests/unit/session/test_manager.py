"""Tests for SessionManager."""

import json
import time
from pathlib import Path

import pytest

from claude_indexer.session.manager import (
    SessionManager,
    clear_session,
    get_session_context,
    list_active_sessions,
)


class TestSessionManager:
    """Tests for SessionManager class."""

    def test_initialize_new_session(self, tmp_path: Path) -> None:
        """Should create new session on initialize."""
        # Create project marker
        (tmp_path / ".git").mkdir()

        manager = SessionManager(project_path=tmp_path)
        context = manager.initialize()

        assert context is not None
        assert context.project_path == tmp_path
        assert context.session_id is not None
        assert len(context.session_id) > 0

    def test_initialize_derives_collection_name(self, tmp_path: Path) -> None:
        """Should derive collection name from project."""
        (tmp_path / ".git").mkdir()

        manager = SessionManager(project_path=tmp_path)
        context = manager.initialize()

        # Collection name should be non-empty and contain prefix
        assert context.collection_name
        assert len(context.collection_name) > 0
        # Should include the prefix (defaults to "claude")
        assert "claude" in context.collection_name.lower()

    def test_initialize_with_explicit_collection(self, tmp_path: Path) -> None:
        """Should use explicit collection name if provided."""
        (tmp_path / ".git").mkdir()

        manager = SessionManager(
            project_path=tmp_path,
            collection_name="custom_collection",
        )
        context = manager.initialize()

        assert context.collection_name == "custom_collection"

    def test_initialize_saves_session_file(self, tmp_path: Path) -> None:
        """Should save session to file."""
        (tmp_path / ".git").mkdir()

        manager = SessionManager(project_path=tmp_path)
        context = manager.initialize()

        session_file = tmp_path / ".claude-indexer" / "session.json"
        assert session_file.exists()

        with open(session_file) as f:
            data = json.load(f)
        assert data["session_id"] == context.session_id

    def test_initialize_resumes_existing_session(self, tmp_path: Path) -> None:
        """Should resume existing valid session."""
        (tmp_path / ".git").mkdir()

        # Use explicit collection name to ensure consistency
        # (without git remote, collection hash is random)
        collection_name = "test_resume_collection"

        # Create first session
        manager1 = SessionManager(
            project_path=tmp_path, collection_name=collection_name
        )
        context1 = manager1.initialize()
        session_id = context1.session_id

        # Create second manager - should load existing
        manager2 = SessionManager(
            project_path=tmp_path, collection_name=collection_name
        )
        context2 = manager2.initialize()

        assert context2.session_id == session_id

    def test_initialize_creates_new_for_expired_session(self, tmp_path: Path) -> None:
        """Should create new session if existing is expired."""
        (tmp_path / ".git").mkdir()

        # Create expired session file
        state_dir = tmp_path / ".claude-indexer"
        state_dir.mkdir()
        session_file = state_dir / "session.json"

        old_time = time.time() - (25 * 3600)  # 25 hours ago
        session_data = {
            "session_id": "old_session",
            "project_path": str(tmp_path),
            "collection_name": "test",
            "created_at": old_time,
            "last_activity": old_time,
        }
        with open(session_file, "w") as f:
            json.dump(session_data, f)

        # Initialize should create new session
        manager = SessionManager(project_path=tmp_path)
        context = manager.initialize()

        assert context.session_id != "old_session"

    def test_get_context_after_initialize(self, tmp_path: Path) -> None:
        """Should return context after initialize."""
        (tmp_path / ".git").mkdir()

        manager = SessionManager(project_path=tmp_path)
        manager.initialize()

        context = manager.get_context()
        assert context is not None

    def test_get_context_before_initialize_raises(self, tmp_path: Path) -> None:
        """Should raise error if context accessed before initialize."""
        manager = SessionManager(project_path=tmp_path)

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.get_context()

    def test_has_context(self, tmp_path: Path) -> None:
        """Should report context status correctly."""
        (tmp_path / ".git").mkdir()

        manager = SessionManager(project_path=tmp_path)
        assert manager.has_context() is False

        manager.initialize()
        assert manager.has_context() is True

    def test_cleanup_releases_lock(self, tmp_path: Path) -> None:
        """Should release lock on cleanup."""
        (tmp_path / ".git").mkdir()

        manager = SessionManager(project_path=tmp_path)
        manager.initialize(acquire_lock=True)

        # Lock should be held
        assert manager._lock is not None

        manager.cleanup()

        # Lock should be released
        assert manager._lock is None

    def test_context_manager(self, tmp_path: Path) -> None:
        """Should work as context manager."""
        (tmp_path / ".git").mkdir()

        with SessionManager(project_path=tmp_path) as manager:
            context = manager.get_context()
            assert context is not None

    def test_session_id_format(self, tmp_path: Path) -> None:
        """Should generate session ID in expected format."""
        (tmp_path / ".git").mkdir()

        manager = SessionManager(project_path=tmp_path)
        context = manager.initialize()

        # Format: {hostname}_{timestamp}_{random}
        parts = context.session_id.split("_")
        assert len(parts) == 3
        assert parts[1].isdigit()  # Timestamp
        assert len(parts[2]) == 4  # 4 hex chars

    def test_auto_detect_project_from_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should auto-detect project from CWD."""
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)

        # No explicit project path
        manager = SessionManager()
        context = manager.initialize()

        assert context.project_path == tmp_path


class TestGetSessionContext:
    """Tests for get_session_context convenience function."""

    def test_get_session_context_explicit_path(self, tmp_path: Path) -> None:
        """Should create context with explicit path."""
        (tmp_path / ".git").mkdir()

        context = get_session_context(project=str(tmp_path))

        assert context.project_path == tmp_path

    def test_get_session_context_explicit_collection(self, tmp_path: Path) -> None:
        """Should use explicit collection name."""
        (tmp_path / ".git").mkdir()

        context = get_session_context(
            project=str(tmp_path),
            collection="explicit_coll",
        )

        assert context.collection_name == "explicit_coll"


class TestClearSession:
    """Tests for clear_session function."""

    def test_clear_existing_session(self, tmp_path: Path) -> None:
        """Should clear existing session file."""
        (tmp_path / ".git").mkdir()

        # Create session
        manager = SessionManager(project_path=tmp_path)
        manager.initialize()

        session_file = tmp_path / ".claude-indexer" / "session.json"
        assert session_file.exists()

        # Clear it
        result = clear_session(project=str(tmp_path))

        assert result is True
        assert not session_file.exists()

    def test_clear_nonexistent_session(self, tmp_path: Path) -> None:
        """Should return False for nonexistent session."""
        result = clear_session(project=str(tmp_path))

        assert result is False


class TestListActiveSessions:
    """Tests for list_active_sessions function."""

    def test_list_finds_sessions(self, tmp_path: Path) -> None:
        """Should find active sessions."""
        # Create a project with session
        project = tmp_path / "myproject"
        project.mkdir()
        (project / ".git").mkdir()

        manager = SessionManager(project_path=project)
        context = manager.initialize()

        # List sessions starting from tmp_path
        sessions = list_active_sessions(tmp_path)

        assert len(sessions) >= 1
        found = any(s["session_id"] == context.session_id for s in sessions)
        assert found

    def test_list_marks_stale(self, tmp_path: Path) -> None:
        """Should mark stale sessions."""
        # Create stale session
        state_dir = tmp_path / "project" / ".claude-indexer"
        state_dir.mkdir(parents=True)

        old_time = time.time() - (25 * 3600)
        session_data = {
            "session_id": "stale",
            "project_path": str(tmp_path / "project"),
            "collection_name": "test",
            "last_activity": old_time,
        }
        with open(state_dir / "session.json", "w") as f:
            json.dump(session_data, f)

        sessions = list_active_sessions(tmp_path)

        stale_sessions = [s for s in sessions if s.get("_is_stale")]
        assert len(stale_sessions) >= 1

    def test_list_empty_directory(self, tmp_path: Path) -> None:
        """Should return empty list for directory without sessions."""
        sessions = list_active_sessions(tmp_path)
        assert sessions == []
