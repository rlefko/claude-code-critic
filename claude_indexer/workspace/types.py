"""
Type definitions for workspace support.

This module defines the core data structures for workspace detection and management,
including workspace types, collection strategies, and workspace configuration.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class WorkspaceType(Enum):
    """Detected workspace type.

    Different workspace types have different detection markers and
    default collection strategies.
    """

    NONE = "none"  # Single project (no workspace)
    VSCODE_MULTI_ROOT = "vscode"  # .code-workspace file
    PNPM = "pnpm"  # pnpm-workspace.yaml
    LERNA = "lerna"  # lerna.json
    NX = "nx"  # nx.json
    NPM_WORKSPACES = "npm"  # package.json with workspaces field
    YARN_WORKSPACES = "yarn"  # package.json with workspaces + yarn.lock
    TURBOREPO = "turbo"  # turbo.json


class CollectionStrategy(Enum):
    """How to handle collections for a workspace.

    SINGLE: One collection for entire workspace (monorepos)
    MULTIPLE: Separate collection per folder (VS Code multi-root)
    """

    SINGLE = "single"  # One collection for entire workspace
    MULTIPLE = "multiple"  # Separate collection per folder


@dataclass
class WorkspaceMember:
    """A member/folder within a workspace.

    Represents a single project or package within a workspace,
    with optional per-member configuration overrides.

    Attributes:
        name: Human-readable name for the member
        path: Absolute path to the member directory
        relative_path: Path relative to workspace root
        is_root: True if this represents the workspace root itself
        collection_override: Override default collection name
        exclude_from_workspace: Exclude from workspace indexing
        custom_config: Per-member configuration overrides
    """

    name: str
    path: Path
    relative_path: str
    is_root: bool = False
    collection_override: str | None = None
    exclude_from_workspace: bool = False
    custom_config: dict[str, Any] | None = None

    def __post_init__(self):
        """Ensure path is a Path object."""
        if isinstance(self.path, str):
            self.path = Path(self.path)


@dataclass
class WorkspaceConfig:
    """Configuration for a workspace.

    Contains all detected workspace information including type,
    root path, members, and collection strategy.

    Attributes:
        workspace_type: Type of workspace detected
        root_path: Absolute path to workspace root
        members: List of workspace members/folders
        collection_strategy: How collections should be created
        collection_name: Collection name for SINGLE strategy
        collection_prefix: Prefix for collection names
        include_patterns: Workspace-level include patterns
        exclude_patterns: Workspace-level exclude patterns
        workspace_file: Path to workspace config file (.code-workspace, etc.)
    """

    workspace_type: WorkspaceType
    root_path: Path
    members: list[WorkspaceMember] = field(default_factory=list)
    collection_strategy: CollectionStrategy = CollectionStrategy.SINGLE
    collection_name: str | None = None
    collection_prefix: str = "claude"
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    workspace_file: Path | None = None

    def __post_init__(self):
        """Ensure path objects and derive collection name."""
        if isinstance(self.root_path, str):
            self.root_path = Path(self.root_path)
        if self.workspace_file and isinstance(self.workspace_file, str):
            self.workspace_file = Path(self.workspace_file)

        # Auto-derive collection name if not set
        if self.collection_name is None and self.workspace_type != WorkspaceType.NONE:
            self.collection_name = self._derive_collection_name()

    def _derive_collection_name(self) -> str:
        """Derive collection name from workspace root."""
        name = self.root_path.name.lower()
        # Sanitize: only alphanumeric, underscore, hyphen
        sanitized = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        # Remove consecutive underscores
        while "__" in sanitized:
            sanitized = sanitized.replace("__", "_")
        sanitized = sanitized.strip("_-") or "workspace"

        # Add hash for uniqueness
        hash_input = str(self.root_path).encode()
        hash_suffix = hashlib.sha256(hash_input).hexdigest()[:6]

        return f"{self.collection_prefix}_{sanitized}_{hash_suffix}"

    def get_effective_collection(self, member: WorkspaceMember | None = None) -> str:
        """Get collection name for a member or workspace.

        For SINGLE strategy, returns the workspace collection.
        For MULTIPLE strategy, returns member-specific collection.

        Args:
            member: Optional member to get collection for

        Returns:
            Collection name string
        """
        if self.collection_strategy == CollectionStrategy.MULTIPLE and member:
            if member.collection_override:
                return member.collection_override
            # Derive from member path
            return f"{self.collection_prefix}_{member.name}_{self._hash_member(member)}"

        return self.collection_name or f"{self.collection_prefix}_workspace"

    def _hash_member(self, member: WorkspaceMember) -> str:
        """Generate hash for member collection name.

        Args:
            member: WorkspaceMember to hash

        Returns:
            6-character hex hash
        """
        return hashlib.sha256(str(member.path).encode()).hexdigest()[:6]

    def is_monorepo(self) -> bool:
        """Check if this is a monorepo workspace type.

        Returns:
            True if workspace type is a monorepo variant
        """
        return self.workspace_type in (
            WorkspaceType.PNPM,
            WorkspaceType.LERNA,
            WorkspaceType.NX,
            WorkspaceType.NPM_WORKSPACES,
            WorkspaceType.YARN_WORKSPACES,
            WorkspaceType.TURBOREPO,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "workspace_type": self.workspace_type.value,
            "root_path": str(self.root_path),
            "members": [
                {
                    "name": m.name,
                    "path": str(m.path),
                    "relative_path": m.relative_path,
                    "is_root": m.is_root,
                    "exclude": m.exclude_from_workspace,
                }
                for m in self.members
            ],
            "collection_strategy": self.collection_strategy.value,
            "collection_name": self.collection_name,
            "collection_prefix": self.collection_prefix,
            "workspace_file": str(self.workspace_file) if self.workspace_file else None,
        }
