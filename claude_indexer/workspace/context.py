"""
Workspace context for session management.

This module provides the WorkspaceContext dataclass that tracks workspace
session state, including member collections and active member selection.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import CollectionStrategy, WorkspaceConfig, WorkspaceMember, WorkspaceType


@dataclass
class WorkspaceContext:
    """Context for a workspace session.

    Extends the concept of SessionContext for workspace scenarios,
    tracking multiple members and their configurations.

    This is the primary state object for workspace sessions, containing
    all information needed to work with a workspace.

    Attributes:
        workspace_id: Unique identifier for this workspace session
        workspace_config: Detected workspace configuration
        active_member: Currently active member (for scoped operations)
        member_collections: Mapping of member names to collection names
        created_at: Timestamp of context creation
        last_activity: Timestamp of last activity
    """

    workspace_id: str
    workspace_config: WorkspaceConfig
    active_member: WorkspaceMember | None = None
    member_collections: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def __post_init__(self):
        """Initialize member collections mapping if not provided."""
        if not self.member_collections:
            self._build_collection_mapping()

    def _build_collection_mapping(self):
        """Build member name to collection name mapping."""
        for member in self.workspace_config.members:
            collection = self.workspace_config.get_effective_collection(member)
            self.member_collections[member.name] = collection

    @property
    def is_monorepo(self) -> bool:
        """Check if this is a monorepo workspace.

        Returns:
            True if workspace type is a monorepo variant
        """
        return self.workspace_config.workspace_type in (
            WorkspaceType.PNPM,
            WorkspaceType.LERNA,
            WorkspaceType.NX,
            WorkspaceType.NPM_WORKSPACES,
            WorkspaceType.YARN_WORKSPACES,
            WorkspaceType.TURBOREPO,
        )

    @property
    def is_multi_root(self) -> bool:
        """Check if this is a VS Code multi-root workspace.

        Returns:
            True if workspace is VS Code multi-root
        """
        return self.workspace_config.workspace_type == WorkspaceType.VSCODE_MULTI_ROOT

    @property
    def root_path(self) -> Path:
        """Get workspace root path.

        Returns:
            Path to workspace root directory
        """
        return self.workspace_config.root_path

    @property
    def state_dir(self) -> Path:
        """Get workspace state directory.

        Returns:
            Path to .claude-indexer directory
        """
        return self.root_path / ".claude-indexer"

    @property
    def members(self) -> list[WorkspaceMember]:
        """Get all workspace members.

        Returns:
            List of WorkspaceMember objects
        """
        return self.workspace_config.members

    @property
    def collection_names(self) -> list[str]:
        """Get all collection names for this workspace.

        Returns:
            List of collection names
        """
        if self.workspace_config.collection_strategy == CollectionStrategy.SINGLE:
            collection = self.workspace_config.get_effective_collection()
            return [collection] if collection else []
        else:
            return list(self.member_collections.values())

    def get_collection_for_path(self, file_path: Path) -> str:
        """Get collection name for a file path.

        Determines which member (if any) contains the file
        and returns the appropriate collection.

        For monorepos, always returns the single collection.
        For multi-root, finds the containing member's collection.

        Args:
            file_path: Path to file

        Returns:
            Collection name for the file
        """
        file_path = Path(file_path).resolve()

        # For monorepos, always return the single collection
        if self.is_monorepo:
            return self.workspace_config.get_effective_collection()

        # For multi-root, find the containing member
        for member in self.workspace_config.members:
            try:
                file_path.relative_to(member.path)
                return self.member_collections.get(
                    member.name,
                    self.workspace_config.get_effective_collection(member),
                )
            except ValueError:
                continue

        # Fallback to workspace-level collection
        return self.workspace_config.get_effective_collection()

    def get_member_for_path(self, file_path: Path) -> WorkspaceMember | None:
        """Get workspace member containing a file path.

        Args:
            file_path: Path to file

        Returns:
            WorkspaceMember containing the file, or None
        """
        file_path = Path(file_path).resolve()

        for member in self.workspace_config.members:
            try:
                file_path.relative_to(member.path)
                return member
            except ValueError:
                continue

        return None

    def set_active_member(self, member_name: str) -> bool:
        """Set the active member by name.

        Args:
            member_name: Name of member to activate

        Returns:
            True if member was found and set, False otherwise
        """
        for member in self.workspace_config.members:
            if member.name == member_name:
                self.active_member = member
                return True
        return False

    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def age_seconds(self) -> float:
        """Get age of context in seconds since last activity.

        Returns:
            Number of seconds since last activity
        """
        return time.time() - self.last_activity

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "workspace_id": self.workspace_id,
            "workspace_type": self.workspace_config.workspace_type.value,
            "root_path": str(self.root_path),
            "collection_strategy": self.workspace_config.collection_strategy.value,
            "collection_name": self.workspace_config.collection_name,
            "members": [
                {
                    "name": m.name,
                    "path": str(m.path),
                    "relative_path": m.relative_path,
                }
                for m in self.workspace_config.members
            ],
            "member_collections": self.member_collections,
            "active_member": self.active_member.name if self.active_member else None,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], workspace_config: WorkspaceConfig
    ) -> "WorkspaceContext":
        """Create WorkspaceContext from dictionary.

        Args:
            data: Dictionary representation
            workspace_config: WorkspaceConfig to use

        Returns:
            WorkspaceContext instance
        """
        context = cls(
            workspace_id=data["workspace_id"],
            workspace_config=workspace_config,
            member_collections=data.get("member_collections", {}),
            created_at=data.get("created_at", time.time()),
            last_activity=data.get("last_activity", time.time()),
        )

        # Set active member if specified
        active_member_name = data.get("active_member")
        if active_member_name:
            context.set_active_member(active_member_name)

        return context
