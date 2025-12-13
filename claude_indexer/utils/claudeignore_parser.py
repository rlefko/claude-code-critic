"""Gitignore-compatible .claudeignore parser using pathspec library.

This module provides a parser that correctly handles gitignore-style patterns
including negation patterns, globstar (**), and directory markers.

Example usage:
    parser = ClaudeIgnoreParser(project_root)
    parser.load_file(Path(".claudeignore"))

    if parser.matches("src/secret.key"):
        print("File should be ignored")

    included = parser.filter_paths(all_files)
"""

from collections.abc import Iterable
from pathlib import Path

import pathspec


class ClaudeIgnoreParser:
    """Gitignore-compatible pattern matcher using pathspec library.

    Supports:
    - Standard glob patterns (*.py, *.log)
    - Directory patterns ending with / (node_modules/)
    - Globstar patterns (**/test)
    - Negation patterns (!important.log)
    - Comments starting with #
    - Root-relative patterns starting with /
    """

    def __init__(self, project_root: Path | str):
        """Initialize parser for a project.

        Args:
            project_root: Path to the project root directory.
        """
        self.project_root = Path(project_root).resolve()
        self._patterns: list[str] = []
        self._spec: pathspec.PathSpec | None = None

    def load_file(self, ignore_file: Path | str) -> int:
        """Load patterns from a .claudeignore or .gitignore file.

        Args:
            ignore_file: Path to the ignore file (absolute or relative to project root).

        Returns:
            Number of patterns loaded from the file.
        """
        ignore_path = Path(ignore_file)
        if not ignore_path.is_absolute():
            ignore_path = self.project_root / ignore_path

        if not ignore_path.exists():
            return 0

        count_before = len(self._patterns)

        try:
            with open(ignore_path, encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n\r")

                    # Skip empty lines and comments
                    # Note: \# is handled by pathspec for literal #
                    stripped = line.lstrip()
                    if not stripped or stripped.startswith("#"):
                        continue

                    self._patterns.append(stripped)

        except OSError as e:
            # Log but don't fail - file may be temporarily unavailable
            import logging

            logging.getLogger(__name__).warning(f"Could not read {ignore_path}: {e}")
            return 0

        self._rebuild_spec()
        return len(self._patterns) - count_before

    def add_patterns(self, patterns: list[str]) -> None:
        """Add patterns programmatically.

        Args:
            patterns: List of gitignore-style patterns to add.
        """
        for pattern in patterns:
            pattern = pattern.strip()
            if pattern and not pattern.startswith("#"):
                self._patterns.append(pattern)

        self._rebuild_spec()

    def _rebuild_spec(self) -> None:
        """Rebuild the pathspec from current patterns."""
        if not self._patterns:
            self._spec = None
            return

        # Use gitwildmatch for proper gitignore semantics
        self._spec = pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern, self._patterns
        )

    def matches(self, path: Path | str) -> bool:
        """Check if a path should be ignored.

        Args:
            path: Path to check (can be absolute or relative to project root).

        Returns:
            True if the path matches an ignore pattern (should be ignored).
        """
        if self._spec is None:
            return False

        # Convert to string path relative to project root
        path = Path(path)
        if path.is_absolute():
            # Resolve to handle symlinks (e.g., /var -> /private/var on macOS)
            try:
                path = path.resolve().relative_to(self.project_root)
            except ValueError:
                # Path is not under project root - can't match
                return False

        # pathspec expects forward slashes
        path_str = str(path).replace("\\", "/")

        return self._spec.match_file(path_str)

    def filter_paths(self, paths: Iterable[Path | str]) -> list[Path]:
        """Filter a list of paths, returning only those NOT ignored.

        Args:
            paths: Iterable of paths to filter.

        Returns:
            List of paths that should be included (not ignored).
        """
        result = []
        for path in paths:
            if not self.matches(path):
                result.append(Path(path) if not isinstance(path, Path) else path)
        return result

    def get_matching_pattern(self, path: Path | str) -> str | None:
        """Get the pattern that matches a path (for debugging).

        Args:
            path: Path to check.

        Returns:
            The matching pattern string, or None if not matched.
        """
        if self._spec is None:
            return None

        path = Path(path)
        if path.is_absolute():
            # Resolve to handle symlinks (e.g., /var -> /private/var on macOS)
            try:
                path = path.resolve().relative_to(self.project_root)
            except ValueError:
                return None

        path_str = str(path).replace("\\", "/")

        # Check each pattern individually to find the matching one
        for pattern in self._patterns:
            spec = pathspec.PathSpec.from_lines(
                pathspec.patterns.GitWildMatchPattern, [pattern]
            )
            if spec.match_file(path_str):
                # For negation patterns, continue checking
                if pattern.startswith("!"):
                    continue
                return pattern

        return None

    @property
    def patterns(self) -> list[str]:
        """Return all loaded patterns."""
        return self._patterns.copy()

    @property
    def pattern_count(self) -> int:
        """Return the number of patterns loaded."""
        return len(self._patterns)

    def clear(self) -> None:
        """Clear all loaded patterns."""
        self._patterns.clear()
        self._spec = None
