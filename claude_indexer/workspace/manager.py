"""
Workspace manager for orchestrating workspace operations.

This module provides the WorkspaceManager class that handles the complete
lifecycle of workspace sessions, including detection, initialization,
collection management, and state persistence.
"""

import contextlib
import json
import secrets
import socket
import time
from pathlib import Path

from ..config.config_loader import ConfigLoader
from ..indexer_logging import get_logger
from .config import WorkspaceConfigLoader
from .context import WorkspaceContext
from .detector import WorkspaceDetector
from .types import CollectionStrategy, WorkspaceConfig, WorkspaceMember, WorkspaceType

logger = get_logger()


class WorkspaceManager:
    """Manages workspace lifecycle and operations.

    The WorkspaceManager is the primary interface for working with workspaces.
    It handles detection, initialization, state management, and provides
    methods for working with workspace members.

    Responsibilities:
    - Detect and initialize workspaces
    - Coordinate member configuration
    - Manage workspace-level state
    - Handle collection creation/cleanup

    Example:
        manager = WorkspaceManager()
        context = manager.initialize()

        if context.is_monorepo:
            # Index entire monorepo to single collection
            print(f"Indexing monorepo: {context.root_path}")
        else:
            # Index each folder separately
            for member in context.members:
                print(f"Indexing: {member.name}")

        # Context manager support
        with WorkspaceManager() as manager:
            context = manager.initialize()
            # Work with workspace
    """

    WORKSPACE_STATE_FILE = "workspace.json"
    WORKSPACE_TTL_HOURS = 24.0

    def __init__(
        self,
        workspace_path: Path | None = None,
        config_loader: ConfigLoader | None = None,
    ):
        """Initialize workspace manager.

        Args:
            workspace_path: Explicit workspace path (auto-detect if None)
            config_loader: Optional base config loader for settings
        """
        self._explicit_path = workspace_path
        self.config_loader = config_loader or ConfigLoader()
        self._context: WorkspaceContext | None = None
        self._workspace_config: WorkspaceConfig | None = None
        self._ws_config_loader: WorkspaceConfigLoader | None = None

    def detect(self) -> WorkspaceConfig:
        """Detect workspace configuration.

        Scans for workspace markers starting from the configured or current path.

        Returns:
            WorkspaceConfig with detected type and members
        """
        if self._workspace_config is not None:
            return self._workspace_config

        start_path = self._explicit_path or Path.cwd()
        self._workspace_config = WorkspaceDetector.detect(start_path)

        return self._workspace_config

    def is_workspace(self) -> bool:
        """Check if current path is within a workspace.

        Returns:
            True if a workspace was detected
        """
        config = self.detect()
        return config.workspace_type != WorkspaceType.NONE

    def initialize(self) -> WorkspaceContext:
        """Initialize or resume workspace session.

        Creates a new workspace context or resumes an existing one
        if a valid session state exists.

        Returns:
            WorkspaceContext for the workspace

        Raises:
            ValueError: If not in a workspace
        """
        if self._context is not None:
            return self._context

        workspace_config = self.detect()

        if workspace_config.workspace_type == WorkspaceType.NONE:
            raise ValueError(
                "Not in a workspace. Use 'claude-indexer init' for single projects."
            )

        # Try to load existing context
        existing = self._load_existing_context(workspace_config)
        if existing:
            logger.debug(f"Resuming workspace session: {existing.workspace_id}")
            self._context = existing
            self._context.touch()
            self._save_context()
            return self._context

        # Create new context
        workspace_id = self._generate_workspace_id()
        self._context = WorkspaceContext(
            workspace_id=workspace_id,
            workspace_config=workspace_config,
        )

        self._save_context()
        logger.info(
            f"Initialized {workspace_config.workspace_type.value} workspace "
            f"with {len(workspace_config.members)} members"
        )

        return self._context

    def _generate_workspace_id(self) -> str:
        """Generate unique workspace ID.

        Format: ws_{hostname}_{timestamp}_{random}

        Returns:
            Unique workspace ID string
        """
        hostname = socket.gethostname()[:8].lower()
        hostname = "".join(c for c in hostname if c.isalnum()) or "host"
        timestamp = int(time.time())
        random_suffix = secrets.token_hex(2)
        return f"ws_{hostname}_{timestamp}_{random_suffix}"

    def _get_state_dir(self) -> Path:
        """Get workspace state directory.

        Returns:
            Path to .claude-indexer directory
        """
        config = self.detect()
        return config.root_path / ".claude-indexer"

    def _get_state_file(self) -> Path:
        """Get workspace state file path.

        Returns:
            Path to workspace.json
        """
        return self._get_state_dir() / self.WORKSPACE_STATE_FILE

    def _load_existing_context(
        self, workspace_config: WorkspaceConfig
    ) -> WorkspaceContext | None:
        """Load existing workspace context if valid.

        Validates that the saved context matches the current workspace
        and has not expired.

        Args:
            workspace_config: Current workspace configuration

        Returns:
            WorkspaceContext if valid, None otherwise
        """
        state_file = self._get_state_file()
        if not state_file.exists():
            return None

        try:
            with open(state_file) as f:
                data = json.load(f)

            # Validate workspace matches
            if data.get("root_path") != str(workspace_config.root_path):
                logger.debug("Workspace root path mismatch, creating new session")
                return None
            if data.get("workspace_type") != workspace_config.workspace_type.value:
                logger.debug("Workspace type mismatch, creating new session")
                return None

            # Check TTL
            last_activity = data.get("last_activity", 0)
            age_hours = (time.time() - last_activity) / 3600
            if age_hours > self.WORKSPACE_TTL_HOURS:
                logger.debug("Workspace session expired, creating new session")
                return None

            return WorkspaceContext.from_dict(data, workspace_config)
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.debug(f"Could not load workspace context: {e}")
            return None

    def _save_context(self):
        """Save workspace context to state file."""
        if self._context is None:
            return

        state_dir = self._get_state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)

        state_file = self._get_state_file()
        temp_file = state_file.with_suffix(".tmp")

        try:
            with open(temp_file, "w") as f:
                json.dump(self._context.to_dict(), f, indent=2)
            temp_file.replace(state_file)
        except OSError as e:
            logger.debug(f"Could not save workspace context: {e}")
            if temp_file.exists():
                with contextlib.suppress(OSError):
                    temp_file.unlink()

    def get_config_loader(self) -> WorkspaceConfigLoader:
        """Get workspace configuration loader.

        Returns:
            WorkspaceConfigLoader for this workspace
        """
        if self._ws_config_loader is None:
            self._ws_config_loader = WorkspaceConfigLoader(
                self.detect(), self.config_loader
            )
        return self._ws_config_loader

    def get_indexing_paths(self) -> list[Path]:
        """Get all paths that should be indexed.

        For monorepos, returns the workspace root path.
        For multi-root, returns individual member paths.

        Returns:
            List of paths to index
        """
        context = self.initialize()

        if context.is_monorepo:
            # Return workspace root - indexer will handle all members
            return [context.root_path]
        else:
            # Return individual member paths
            return [m.path for m in context.members]

    def get_member_by_name(self, name: str) -> WorkspaceMember | None:
        """Get workspace member by name.

        Args:
            name: Member name to find

        Returns:
            WorkspaceMember or None if not found
        """
        workspace_config = self.detect()
        for member in workspace_config.members:
            if member.name == name:
                return member
        return None

    def get_member_by_path(self, path: Path) -> WorkspaceMember | None:
        """Get workspace member containing a path.

        Args:
            path: File or directory path

        Returns:
            WorkspaceMember containing the path, or None
        """
        path = Path(path).resolve()
        workspace_config = self.detect()

        for member in workspace_config.members:
            try:
                path.relative_to(member.path)
                return member
            except ValueError:
                continue

        return None

    def get_collection_for_member(self, member_name: str) -> str | None:
        """Get collection name for a member.

        Args:
            member_name: Name of the member

        Returns:
            Collection name or None if member not found
        """
        member = self.get_member_by_name(member_name)
        if member is None:
            return None

        workspace_config = self.detect()
        return workspace_config.get_effective_collection(member)

    def get_all_collections(self) -> list[str]:
        """Get all collection names for the workspace.

        Returns:
            List of collection names
        """
        workspace_config = self.detect()

        if workspace_config.collection_strategy == CollectionStrategy.SINGLE:
            return [workspace_config.get_effective_collection()]
        else:
            return [
                workspace_config.get_effective_collection(m)
                for m in workspace_config.members
            ]

    def create_workspace_config(self) -> Path:
        """Create workspace configuration file.

        Generates workspace.config.json with detected settings.

        Returns:
            Path to created config file
        """
        config_loader = self.get_config_loader()
        return config_loader.create_workspace_config()

    def cleanup(self):
        """Cleanup workspace resources.

        Saves final state before cleanup.
        """
        if self._context is not None:
            self._context.touch()
            self._save_context()

    def clear_session(self) -> bool:
        """Clear workspace session state.

        Removes the workspace.json state file.

        Returns:
            True if session was cleared, False if no session existed
        """
        state_file = self._get_state_file()
        if state_file.exists():
            try:
                state_file.unlink()
                self._context = None
                logger.info("Cleared workspace session")
                return True
            except OSError as e:
                logger.warning(f"Could not clear workspace session: {e}")
                return False
        return False

    def __enter__(self) -> "WorkspaceManager":
        """Context manager entry.

        Returns:
            Self for use in with statement
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit.

        Performs cleanup on exit.
        """
        self.cleanup()


def get_workspace_context(
    workspace_path: str | None = None,
) -> WorkspaceContext | None:
    """Get workspace context if in a workspace.

    Convenience function for quickly checking if the current or specified
    path is within a workspace and getting its context.

    Args:
        workspace_path: Optional explicit workspace path

    Returns:
        WorkspaceContext if in workspace, None otherwise
    """
    manager = WorkspaceManager(
        workspace_path=Path(workspace_path) if workspace_path else None
    )

    if not manager.is_workspace():
        return None

    try:
        return manager.initialize()
    except ValueError:
        return None


def detect_workspace(path: str | None = None) -> WorkspaceConfig:
    """Detect workspace configuration.

    Convenience function for detecting workspace type and members.

    Args:
        path: Optional path to check (defaults to CWD)

    Returns:
        WorkspaceConfig with detected information
    """
    return WorkspaceDetector.detect(Path(path) if path else None)
