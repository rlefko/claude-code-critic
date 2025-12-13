"""Tests for LockManager."""

import json
import os
import time
from pathlib import Path

from claude_indexer.session.lock import LockConflictError, LockManager


class TestLockManager:
    """Tests for LockManager class."""

    def test_acquire_lock(self, tmp_path: Path) -> None:
        """Should acquire lock on file."""
        lock_path = tmp_path / "test.lock"
        lock = LockManager(lock_path, session_id="test_session")

        assert lock.acquire() is True
        assert lock.is_locked() is True
        assert lock_path.exists()

        lock.release()

    def test_release_lock(self, tmp_path: Path) -> None:
        """Should release lock."""
        lock_path = tmp_path / "test.lock"
        lock = LockManager(lock_path)

        lock.acquire()
        lock.release()

        assert lock.is_locked() is False

    def test_context_manager(self, tmp_path: Path) -> None:
        """Should work as context manager."""
        lock_path = tmp_path / "test.lock"

        with LockManager(lock_path, session_id="ctx_session") as lock:
            assert lock.is_locked() is True

        # Lock should be released after context
        assert lock.is_locked() is False

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if needed."""
        lock_path = tmp_path / "nested" / "dirs" / "test.lock"

        with LockManager(lock_path) as lock:
            assert lock_path.exists()
            assert lock.is_locked()

    def test_lock_holder_info(self, tmp_path: Path) -> None:
        """Should write holder info to lock file."""
        lock_path = tmp_path / "test.lock"

        with LockManager(lock_path, session_id="holder_test"):
            holder_info = LockManager.check_lock_holder(lock_path)

            assert holder_info is not None
            assert holder_info["session_id"] == "holder_test"
            assert holder_info["pid"] == os.getpid()
            assert "hostname" in holder_info
            assert "acquired_at" in holder_info

    def test_check_lock_holder_no_file(self, tmp_path: Path) -> None:
        """Should return None if lock file doesn't exist."""
        lock_path = tmp_path / "nonexistent.lock"

        holder_info = LockManager.check_lock_holder(lock_path)

        assert holder_info is None

    def test_non_blocking_acquire_fails(self, tmp_path: Path) -> None:
        """Should return False for non-blocking acquire when locked."""
        lock_path = tmp_path / "test.lock"

        # First lock
        lock1 = LockManager(lock_path)
        assert lock1.acquire(blocking=False) is True

        # Second lock attempt (non-blocking)
        lock2 = LockManager(lock_path)
        assert lock2.acquire(blocking=False) is False

        lock1.release()

    def test_double_acquire_same_instance(self, tmp_path: Path) -> None:
        """Should handle double acquire on same instance."""
        lock_path = tmp_path / "test.lock"
        lock = LockManager(lock_path)

        assert lock.acquire() is True
        assert lock.acquire() is True  # Should succeed (already held)
        assert lock.is_locked() is True

        lock.release()

    def test_double_release_safe(self, tmp_path: Path) -> None:
        """Should safely handle double release."""
        lock_path = tmp_path / "test.lock"
        lock = LockManager(lock_path)

        lock.acquire()
        lock.release()
        lock.release()  # Should not raise

    def test_is_stale_no_file(self, tmp_path: Path) -> None:
        """Should return True if lock file doesn't exist."""
        lock_path = tmp_path / "nonexistent.lock"

        assert LockManager.is_stale(lock_path) is True

    def test_is_stale_old_lock(self, tmp_path: Path) -> None:
        """Should return True for old lock."""
        lock_path = tmp_path / "test.lock"

        # Create lock file with old timestamp
        old_time = time.time() - (25 * 3600)  # 25 hours ago
        holder_info = {
            "session_id": "old_session",
            "pid": 99999999,  # Likely non-existent PID
            "hostname": "old_host",
            "acquired_at": old_time,
        }
        lock_path.write_text(json.dumps(holder_info))

        assert LockManager.is_stale(lock_path, max_age_hours=24.0) is True

    def test_cleanup_stale_lock(self, tmp_path: Path) -> None:
        """Should remove stale lock file."""
        lock_path = tmp_path / "test.lock"

        # Create stale lock file
        old_time = time.time() - (25 * 3600)
        holder_info = {
            "session_id": "stale_session",
            "pid": 99999999,
            "acquired_at": old_time,
        }
        lock_path.write_text(json.dumps(holder_info))

        assert lock_path.exists()
        result = LockManager.cleanup_stale_lock(lock_path)

        assert result is True
        assert not lock_path.exists()

    def test_cleanup_active_lock(self, tmp_path: Path) -> None:
        """Should not remove active lock file."""
        lock_path = tmp_path / "test.lock"

        with LockManager(lock_path, session_id="active"):
            result = LockManager.cleanup_stale_lock(lock_path)

            assert result is False
            assert lock_path.exists()


class TestLockConflictError:
    """Tests for LockConflictError exception."""

    def test_error_with_holder_info(self) -> None:
        """Should include holder info in message."""
        holder = {
            "session_id": "other_session",
            "pid": 12345,
        }
        error = LockConflictError(Path("/test.lock"), holder)

        assert "other_session" in str(error)
        assert "12345" in str(error)

    def test_error_without_holder_info(self) -> None:
        """Should handle missing holder info."""
        error = LockConflictError(Path("/test.lock"))

        assert "test.lock" in str(error)

    def test_error_with_custom_message(self) -> None:
        """Should allow custom message."""
        error = LockConflictError(
            Path("/test.lock"),
            message="Custom conflict message",
        )

        assert str(error) == "Custom conflict message"

    def test_error_attributes(self) -> None:
        """Should expose lock_path and holder_info."""
        path = Path("/test.lock")
        holder = {"session_id": "test"}

        error = LockConflictError(path, holder)

        assert error.lock_path == path
        assert error.holder_info == holder


class TestLockManagerMultiprocess:
    """Multiprocessing tests for LockManager."""

    def test_concurrent_lock_conflict_single_process(self, tmp_path: Path) -> None:
        """Should detect concurrent lock conflict within single process."""
        lock_path = tmp_path / "concurrent.lock"

        # First lock acquires successfully
        lock1 = LockManager(lock_path, session_id="process1")
        assert lock1.acquire(blocking=False) is True

        # Second lock fails (non-blocking)
        lock2 = LockManager(lock_path, session_id="process2")
        assert lock2.acquire(blocking=False) is False

        # After release, second can acquire
        lock1.release()
        assert lock2.acquire(blocking=False) is True
        lock2.release()
