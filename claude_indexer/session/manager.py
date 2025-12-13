"""
Session manager for Claude Code Memory.

This module provides the SessionManager class that orchestrates session
lifecycle management, including project detection, context creation,
lock acquisition, and cleanup.
"""

import contextlib
import json
import secrets
import socket
import time
from pathlib import Path

from ..config.config_loader import ConfigLoader
from ..config.models import IndexerConfig
from ..indexer_logging import get_logger
from ..init.project_detector import ProjectDetector
from .context import SessionContext
from .detector import ProjectRootDetector
from .lock import LockConflictError, LockManager

logger = get_logger()


class SessionManager:
    """Manages session lifecycle and context.

    Responsibilities:
    - Initialize session from CWD or explicit path
    - Load/create SessionContext
    - Coordinate with LockManager for concurrent access
    - Integrate with ConfigLoader and ProjectDetector

    Example:
        # Auto-detect project from CWD
        manager = SessionManager()
        context = manager.initialize()

        # Or explicit project path
        manager = SessionManager(project_path=Path("/path/to/project"))
        context = manager.initialize()

        # Use context
        print(f"Session: {context.session_id}")
        print(f"Collection: {context.collection_name}")

        # Cleanup when done
        manager.cleanup()
    """

    SESSION_FILE = "session.json"
    STATE_DIR = ".claude-indexer"
    SESSION_TTL_HOURS = 24.0  # Sessions expire after 24 hours

    def __init__(
        self,
        project_path: Path | None = None,
        collection_name: str | None = None,
        config_loader: ConfigLoader | None = None,
    ):
        """Initialize session manager.

        Args:
            project_path: Explicit project path (auto-detect from CWD if None)
            collection_name: Explicit collection name (derive from project if None)
            config_loader: Optional config loader (creates one if not provided)
        """
        self.project_path = self._resolve_project_path(project_path)
        self._explicit_collection = collection_name
        self.config_loader = config_loader or ConfigLoader()
        self._context: SessionContext | None = None
        self._lock: LockManager | None = None
        self._config: IndexerConfig | None = None

    def _resolve_project_path(self, explicit_path: Path | None = None) -> Path:
        """Resolve project path from explicit or CWD detection.

        Args:
            explicit_path: Explicitly provided path, or None for auto-detect

        Returns:
            Resolved absolute path to project root
        """
        if explicit_path:
            return Path(explicit_path).resolve()
        return ProjectRootDetector.detect_from_cwd()

    def initialize(self, acquire_lock: bool = False) -> SessionContext:
        """Initialize or resume session.

        Creates SessionContext with:
        1. Unique session ID (or loads existing if valid)
        2. Project path (detected or explicit)
        3. Collection name (derived or explicit)
        4. Loaded configuration

        Args:
            acquire_lock: If True, acquire exclusive lock on initialization

        Returns:
            Initialized SessionContext

        Raises:
            LockConflictError: If acquire_lock=True and lock cannot be acquired
        """
        if self._context is not None:
            return self._context

        # Load configuration
        self._load_config()

        # Derive collection name
        collection_name = self._derive_collection_name()

        # Try to load existing session
        existing = self._load_existing_session(collection_name)
        if existing:
            logger.debug(f"Resuming existing session: {existing.session_id}")
            self._context = existing
            self._context.touch()
            self._save_session()
        else:
            # Create new session
            session_id = self._generate_session_id()
            self._context = SessionContext(
                session_id=session_id,
                project_path=self.project_path,
                collection_name=collection_name,
                config=self._config,
                created_at=time.time(),
                last_activity=time.time(),
            )
            self._save_session()
            logger.debug(f"Created new session: {session_id}")

        # Optionally acquire lock
        if acquire_lock:
            self.acquire_lock(exclusive=True)

        return self._context

    def _load_config(self) -> None:
        """Load project configuration."""
        try:
            self._config = self.config_loader.load()
        except Exception as e:
            logger.debug(f"Could not load config: {e}")
            self._config = IndexerConfig()

    def _derive_collection_name(self) -> str:
        """Derive collection name from project.

        Uses the explicit collection name if provided, otherwise
        derives from the project path using ProjectDetector.

        Returns:
            Collection name string
        """
        if self._explicit_collection:
            return self._explicit_collection

        # Use ProjectDetector for collection name derivation
        detector = ProjectDetector(self.project_path)
        prefix = self._config.collection_prefix if self._config else "claude"
        return detector.derive_collection_name(
            prefix=prefix,
            include_hash=True,
        )

    def _generate_session_id(self) -> str:
        """Generate unique session ID.

        Format: {short_hostname}_{timestamp}_{random}
        Example: mbp_1702401234_a3f2

        Returns:
            Unique session ID string
        """
        hostname = socket.gethostname()[:8].lower()
        # Remove any non-alphanumeric characters from hostname
        hostname = "".join(c for c in hostname if c.isalnum())
        if not hostname:
            hostname = "host"

        timestamp = int(time.time())
        random_suffix = secrets.token_hex(2)

        return f"{hostname}_{timestamp}_{random_suffix}"

    def _get_state_dir(self) -> Path:
        """Get the state directory path.

        Returns:
            Path to .claude-indexer directory
        """
        return self.project_path / self.STATE_DIR

    def _get_session_file(self) -> Path:
        """Get the session file path.

        Returns:
            Path to session.json
        """
        return self._get_state_dir() / self.SESSION_FILE

    def _load_existing_session(
        self,
        collection_name: str,
    ) -> SessionContext | None:
        """Load existing session if valid.

        Args:
            collection_name: Expected collection name

        Returns:
            SessionContext if valid session exists, None otherwise
        """
        session_file = self._get_session_file()
        if not session_file.exists():
            return None

        try:
            with open(session_file) as f:
                data = json.load(f)

            # Validate session matches this project/collection
            if data.get("collection_name") != collection_name:
                logger.debug("Session collection mismatch, creating new")
                return None
            if str(data.get("project_path")) != str(self.project_path):
                logger.debug("Session project path mismatch, creating new")
                return None

            # Check TTL
            last_activity = data.get("last_activity", 0)
            age_hours = (time.time() - last_activity) / 3600
            if age_hours > self.SESSION_TTL_HOURS:
                logger.debug(f"Session expired ({age_hours:.1f}h old), creating new")
                return None

            return SessionContext.from_dict(data, self._config)

        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Could not load existing session: {e}")
            return None

    def _save_session(self) -> None:
        """Save session to state file."""
        if self._context is None:
            return

        state_dir = self._get_state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)

        session_file = self._get_session_file()
        temp_file = session_file.with_suffix(".tmp")

        try:
            with open(temp_file, "w") as f:
                json.dump(self._context.to_dict(), f, indent=2)
            temp_file.replace(session_file)
        except OSError as e:
            logger.debug(f"Could not save session: {e}")
            if temp_file.exists():
                with contextlib.suppress(OSError):
                    temp_file.unlink()

    def acquire_lock(self, exclusive: bool = True) -> LockManager:
        """Acquire session lock for this collection.

        Args:
            exclusive: True for write operations, False for read-only

        Returns:
            LockManager instance (already locked)

        Raises:
            LockConflictError: If lock cannot be acquired
        """
        if self._context is None:
            raise RuntimeError("Session not initialized. Call initialize() first.")

        if self._lock is not None and self._lock.is_locked():
            return self._lock

        lock_path = self._context.lock_file
        self._lock = LockManager(
            lock_path,
            session_id=self._context.session_id,
        )

        if not self._lock.acquire(exclusive=exclusive, blocking=True):
            holder_info = LockManager.check_lock_holder(lock_path)
            raise LockConflictError(lock_path, holder_info)

        return self._lock

    def release_lock(self) -> None:
        """Release the session lock if held."""
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    def get_context(self) -> SessionContext:
        """Get current session context.

        Returns:
            Current SessionContext

        Raises:
            RuntimeError: If session not initialized
        """
        if self._context is None:
            raise RuntimeError("Session not initialized. Call initialize() first.")
        return self._context

    def has_context(self) -> bool:
        """Check if session context exists.

        Returns:
            True if session has been initialized
        """
        return self._context is not None

    def cleanup(self) -> None:
        """Release locks and cleanup session resources.

        Should be called when session ends.
        """
        self.release_lock()
        # Update last activity before closing
        if self._context is not None:
            self._context.touch()
            self._save_session()

    def __enter__(self) -> "SessionManager":
        """Context manager entry - initialize session."""
        self.initialize()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit - cleanup session."""
        self.cleanup()


def get_session_context(
    project: str | None = None,
    collection: str | None = None,
    config_loader: ConfigLoader | None = None,
) -> SessionContext:
    """Get or create session context for CLI commands.

    Convenience function that creates a SessionManager, initializes
    the session, and returns the context.

    Args:
        project: Explicit project path (auto-detect if None)
        collection: Explicit collection name (derive if None)
        config_loader: Optional config loader

    Returns:
        SessionContext for the session
    """
    manager = SessionManager(
        project_path=Path(project) if project else None,
        collection_name=collection,
        config_loader=config_loader,
    )
    return manager.initialize()


def clear_session(project: str | None = None) -> bool:
    """Clear session state for a project.

    Removes the session.json file to force a new session on next use.

    Args:
        project: Project path (auto-detect if None)

    Returns:
        True if session was cleared, False if no session existed
    """
    project_path = (
        Path(project).resolve() if project else ProjectRootDetector.detect_from_cwd()
    )
    session_file = project_path / SessionManager.STATE_DIR / SessionManager.SESSION_FILE

    if session_file.exists():
        try:
            session_file.unlink()
            logger.info(f"Cleared session for {project_path}")
            return True
        except OSError as e:
            logger.debug(f"Could not clear session: {e}")
            return False
    return False


def list_active_sessions(base_path: Path | None = None) -> list[dict]:
    """List all active sessions.

    Scans for session.json files in .claude-indexer directories.

    Args:
        base_path: Base path to search (defaults to home directory)

    Returns:
        List of session info dictionaries
    """
    sessions = []
    base = base_path or Path.home()

    # Search for .claude-indexer directories
    try:
        for state_dir in base.rglob(f"**/{SessionManager.STATE_DIR}"):
            if not state_dir.is_dir():
                continue

            session_file = state_dir / SessionManager.SESSION_FILE
            if not session_file.exists():
                continue

            try:
                with open(session_file) as f:
                    data = json.load(f)

                # Add file path and check staleness
                data["_session_file"] = str(session_file)
                last_activity = data.get("last_activity", 0)
                age_hours = (time.time() - last_activity) / 3600
                data["_age_hours"] = round(age_hours, 1)
                data["_is_stale"] = age_hours > SessionManager.SESSION_TTL_HOURS

                sessions.append(data)
            except (OSError, json.JSONDecodeError):
                continue
    except (OSError, PermissionError):
        pass

    return sessions
