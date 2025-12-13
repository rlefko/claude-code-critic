"""
Project root detection for session management.

This module provides CWD-based project root detection by walking up the
directory tree looking for project markers.
"""

from pathlib import Path
from typing import ClassVar


class ProjectRootDetector:
    """Find project root by walking up from CWD.

    Looks for project markers in priority order:
    1. .claude-indexer/ (already initialized project)
    2. .git/ (git repository)
    3. package.json (Node.js project)
    4. pyproject.toml (Python project)
    5. setup.py (Python project)
    6. Cargo.toml (Rust project)
    7. go.mod (Go project)
    8. Makefile (generic project)

    Example:
        root = ProjectRootDetector.find_project_root()
        if root:
            print(f"Project root: {root}")
        else:
            print("No project found, using CWD")
    """

    PROJECT_MARKERS: ClassVar[list[str]] = [
        ".claude-indexer",  # Highest priority - already initialized
        ".git",
        "package.json",
        "pyproject.toml",
        "setup.py",
        "Cargo.toml",
        "go.mod",
        "Makefile",
        ".claude",  # Claude Code config directory
    ]

    @classmethod
    def find_project_root(cls, start_path: Path | None = None) -> Path | None:
        """Walk up from start_path to find project root.

        Searches for project markers starting from the given path and
        walking up the directory tree until a marker is found or the
        filesystem root is reached.

        Args:
            start_path: Starting directory (defaults to CWD)

        Returns:
            Path to project root, or None if not found
        """
        current = (start_path or Path.cwd()).resolve()

        # Walk up to root
        while current != current.parent:
            for marker in cls.PROJECT_MARKERS:
                marker_path = current / marker
                if marker_path.exists():
                    return current
            current = current.parent

        # Check root directory as well
        for marker in cls.PROJECT_MARKERS:
            marker_path = current / marker
            if marker_path.exists():
                return current

        return None

    @classmethod
    def detect_from_cwd(cls) -> Path:
        """Find project root from CWD or use CWD as fallback.

        This method never returns None - if no project root is found,
        it falls back to using the current working directory.

        Returns:
            Path to project root (never None - uses CWD as fallback)
        """
        root = cls.find_project_root()
        return root if root else Path.cwd().resolve()

    @classmethod
    def is_project_root(cls, path: Path) -> bool:
        """Check if a path is a project root.

        Args:
            path: Path to check

        Returns:
            True if path contains any project markers
        """
        path = Path(path).resolve()
        return any((path / marker).exists() for marker in cls.PROJECT_MARKERS)

    @classmethod
    def get_project_marker(cls, path: Path) -> str | None:
        """Get the first project marker found at a path.

        Args:
            path: Path to check

        Returns:
            Name of the first marker found, or None
        """
        path = Path(path).resolve()
        for marker in cls.PROJECT_MARKERS:
            if (path / marker).exists():
                return marker
        return None
