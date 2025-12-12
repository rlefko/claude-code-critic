"""
Session context for Claude Code Memory.

This module provides the SessionContext dataclass that tracks all essential
state for a Claude Code session, enabling session isolation.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..config.models import IndexerConfig


@dataclass
class SessionContext:
    """Immutable session context for a Claude Code session.

    Tracks the essential state for session isolation:
    - session_id: Unique ID for this Claude session
    - project_path: Absolute path to project root
    - collection_name: Qdrant collection for this project
    - config: Loaded IndexerConfig
    - created_at: Session creation timestamp

    Example:
        context = SessionContext(
            session_id="mbp_1702401234_a3f2",
            project_path=Path("/path/to/project"),
            collection_name="claude_myproject_abc123",
        )
        print(f"State dir: {context.state_dir}")
        print(f"Lock file: {context.lock_file}")
    """

    session_id: str
    project_path: Path
    collection_name: str
    config: Optional["IndexerConfig"] = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Ensure project_path is a Path object."""
        if isinstance(self.project_path, str):
            self.project_path = Path(self.project_path)
        self.project_path = self.project_path.resolve()

    @property
    def state_dir(self) -> Path:
        """Get .claude-indexer directory for this project.

        Returns:
            Path to the project's .claude-indexer directory
        """
        return self.project_path / ".claude-indexer"

    @property
    def lock_file(self) -> Path:
        """Get lock file path for this session.

        Returns:
            Path to the collection lock file
        """
        return self.state_dir / f"{self.collection_name}.lock"

    @property
    def session_file(self) -> Path:
        """Get session state file path.

        Returns:
            Path to the session.json file
        """
        return self.state_dir / "session.json"

    def touch(self) -> None:
        """Update last_activity timestamp."""
        self.last_activity = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage.

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "session_id": self.session_id,
            "project_path": str(self.project_path),
            "collection_name": self.collection_name,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        config: Optional["IndexerConfig"] = None,
    ) -> "SessionContext":
        """Deserialize from dictionary.

        Args:
            data: Dictionary containing session data
            config: Optional IndexerConfig to attach

        Returns:
            SessionContext instance
        """
        return cls(
            session_id=data["session_id"],
            project_path=Path(data["project_path"]),
            collection_name=data["collection_name"],
            config=config,
            created_at=data.get("created_at", time.time()),
            last_activity=data.get("last_activity", time.time()),
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        return (
            f"SessionContext(id={self.session_id}, "
            f"project={self.project_path.name}, "
            f"collection={self.collection_name})"
        )

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"SessionContext("
            f"session_id={self.session_id!r}, "
            f"project_path={self.project_path!r}, "
            f"collection_name={self.collection_name!r}, "
            f"created_at={self.created_at}, "
            f"last_activity={self.last_activity})"
        )
