"""
File-based locking for session isolation.

This module provides a cross-platform file locking mechanism using fcntl
on Unix systems. Lock files contain metadata about the lock holder for
debugging and conflict reporting.
"""

import contextlib
import fcntl
import json
import os
import socket
import time
from pathlib import Path
from typing import Any

from ..indexer_logging import get_logger

logger = get_logger()


class LockConflictError(Exception):
    """Raised when a lock cannot be acquired due to another session.

    Attributes:
        lock_path: Path to the contested lock file
        holder_info: Information about the current lock holder
    """

    def __init__(
        self,
        lock_path: Path,
        holder_info: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        self.lock_path = lock_path
        self.holder_info = holder_info

        if message:
            super().__init__(message)
        elif holder_info:
            holder_session = holder_info.get("session_id", "unknown")
            holder_pid = holder_info.get("pid", "unknown")
            super().__init__(
                f"Lock conflict: {lock_path} held by session {holder_session} "
                f"(pid: {holder_pid})"
            )
        else:
            super().__init__(f"Lock conflict: {lock_path}")


class LockManager:
    """File-based locking for concurrent session protection.

    Uses fcntl.flock() for advisory locking on Unix systems.
    Lock files are stored in .claude-indexer/{collection}.lock
    and contain metadata about the lock holder.

    Lock behavior:
    - Exclusive lock for writes (state file updates)
    - Shared lock for reads (optional, for consistency)
    - Non-blocking acquire with graceful failure
    - Automatic cleanup via context manager

    Example:
        lock = LockManager(Path("/project/.claude-indexer/myproject.lock"))
        with lock:
            # Perform protected operations
            update_state_file()

        # Or manual control:
        lock = LockManager(path)
        if lock.acquire(blocking=False):
            try:
                do_work()
            finally:
                lock.release()
    """

    def __init__(
        self,
        lock_path: Path,
        session_id: str | None = None,
        timeout_seconds: float = 5.0,
    ):
        """Initialize lock manager.

        Args:
            lock_path: Path to the lock file
            session_id: Optional session ID for lock metadata
            timeout_seconds: Timeout for blocking acquire (default: 5s)
        """
        self.lock_path = Path(lock_path)
        self.session_id = session_id
        self.timeout = timeout_seconds
        self._fd: int | None = None
        self._locked = False

    def acquire(self, exclusive: bool = True, blocking: bool = True) -> bool:
        """Acquire lock on the file.

        Creates the lock file if it doesn't exist and acquires an
        advisory lock using fcntl.

        Args:
            exclusive: True for exclusive (write) lock, False for shared (read)
            blocking: True to wait for lock (up to timeout), False for non-blocking

        Returns:
            True if lock acquired, False if non-blocking and locked by another

        Raises:
            LockConflictError: If blocking=True and lock cannot be acquired
                after timeout
        """
        if self._locked:
            logger.debug(f"Lock already held: {self.lock_path}")
            return True

        # Ensure parent directory exists
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Open the lock file (create if needed)
            self._fd = os.open(
                str(self.lock_path),
                os.O_RDWR | os.O_CREAT,
                0o644,
            )

            # Determine lock flags
            lock_flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            if not blocking:
                lock_flags |= fcntl.LOCK_NB

            # Try to acquire with timeout for blocking mode
            if blocking:
                acquired = self._acquire_with_timeout(lock_flags)
                if not acquired:
                    holder_info = self.check_lock_holder(self.lock_path)
                    os.close(self._fd)
                    self._fd = None
                    raise LockConflictError(self.lock_path, holder_info)
            else:
                try:
                    fcntl.flock(self._fd, lock_flags)
                except OSError:
                    os.close(self._fd)
                    self._fd = None
                    return False

            self._locked = True

            # Write lock holder info
            self._write_holder_info()

            logger.debug(f"Lock acquired: {self.lock_path}")
            return True

        except OSError as e:
            if self._fd is not None:
                with contextlib.suppress(OSError):
                    os.close(self._fd)
                self._fd = None
            logger.debug(f"Failed to acquire lock {self.lock_path}: {e}")
            return False

    def _acquire_with_timeout(self, lock_flags: int) -> bool:
        """Try to acquire lock with timeout.

        Args:
            lock_flags: fcntl lock flags

        Returns:
            True if lock acquired, False on timeout
        """
        start_time = time.time()
        interval = 0.1  # Check every 100ms

        while True:
            try:
                fcntl.flock(self._fd, lock_flags | fcntl.LOCK_NB)
                return True
            except OSError:
                elapsed = time.time() - start_time
                if elapsed >= self.timeout:
                    return False
                time.sleep(interval)

    def _write_holder_info(self) -> None:
        """Write lock holder metadata to lock file."""
        if self._fd is None:
            return

        holder_info = {
            "session_id": self.session_id or "unknown",
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "acquired_at": time.time(),
        }

        try:
            # Truncate and write
            os.ftruncate(self._fd, 0)
            os.lseek(self._fd, 0, os.SEEK_SET)
            os.write(self._fd, json.dumps(holder_info, indent=2).encode())
        except OSError as e:
            # Non-fatal - lock still works without metadata
            logger.debug(f"Could not write lock holder info: {e}")

    def release(self) -> None:
        """Release the lock.

        Safe to call even if lock is not held.
        """
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                logger.debug(f"Lock released: {self.lock_path}")
            except OSError as e:
                logger.debug(f"Error releasing lock: {e}")
            finally:
                self._fd = None
                self._locked = False

    def is_locked(self) -> bool:
        """Check if this instance holds the lock.

        Returns:
            True if lock is currently held
        """
        return self._locked

    @classmethod
    def check_lock_holder(cls, lock_path: Path) -> dict[str, Any] | None:
        """Check who holds the lock (for conflict reporting).

        Reads the lock file metadata to identify the current holder.
        This can be called even when another process holds the lock.

        Args:
            lock_path: Path to the lock file

        Returns:
            Dict with holder info (session_id, pid, hostname, acquired_at)
            or None if lock file doesn't exist or is empty
        """
        try:
            if not lock_path.exists():
                return None

            with open(lock_path) as f:
                content = f.read().strip()
                if not content:
                    return None
                return json.loads(content)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Could not read lock holder info: {e}")
            return None

    @classmethod
    def is_stale(cls, lock_path: Path, max_age_hours: float = 24.0) -> bool:
        """Check if a lock file is stale (process no longer running).

        Args:
            lock_path: Path to the lock file
            max_age_hours: Maximum age before considering stale

        Returns:
            True if lock is stale and can be cleaned up
        """
        holder_info = cls.check_lock_holder(lock_path)
        if not holder_info:
            return True

        # Check if process is still running
        pid = holder_info.get("pid")
        if pid:
            try:
                os.kill(pid, 0)  # Check if process exists
            except (OSError, ProcessLookupError):
                # Process not running - stale lock
                return True

        # Check age
        acquired_at = holder_info.get("acquired_at")
        if acquired_at:
            age_hours = (time.time() - acquired_at) / 3600
            if age_hours > max_age_hours:
                return True

        return False

    @classmethod
    def cleanup_stale_lock(cls, lock_path: Path) -> bool:
        """Remove a stale lock file.

        Args:
            lock_path: Path to the lock file

        Returns:
            True if lock was removed, False otherwise
        """
        if cls.is_stale(lock_path):
            try:
                lock_path.unlink()
                logger.info(f"Cleaned up stale lock: {lock_path}")
                return True
            except OSError as e:
                logger.debug(f"Could not clean up stale lock: {e}")
        return False

    def __enter__(self) -> "LockManager":
        """Context manager entry - acquire exclusive lock.

        Raises:
            LockConflictError: If lock cannot be acquired
        """
        if not self.acquire(exclusive=True, blocking=True):
            holder_info = self.check_lock_holder(self.lock_path)
            raise LockConflictError(self.lock_path, holder_info)
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        """Context manager exit - release lock."""
        self.release()

    def __del__(self) -> None:
        """Destructor - ensure lock is released."""
        self.release()
