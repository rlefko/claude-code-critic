#!/usr/bin/env python3
"""
Gitignore Pattern Detector for Automatic Exclude Configuration.

Reads a project's .gitignore file and converts patterns to indexer-compatible
exclude patterns, ensuring build artifacts and generated files are never indexed.
"""

from pathlib import Path
from typing import List, Set


class GitignoreParser:
    """Parse .gitignore files and convert to indexer exclude patterns."""

    def __init__(self, project_root: Path):
        """Initialize with project root directory."""
        self.project_root = Path(project_root).resolve()
        self.gitignore_path = self.project_root / ".gitignore"

    def parse_gitignore(self) -> List[str]:
        """
        Parse .gitignore and return list of exclude patterns.

        Returns:
            List of patterns suitable for indexer exclude configuration.
        """
        if not self.gitignore_path.exists():
            return []

        patterns = []

        try:
            with open(self.gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue

                    # Skip negation patterns (!) - not supported in simple exclude
                    if line.startswith('!'):
                        continue

                    # Convert gitignore pattern to indexer pattern
                    pattern = self._convert_pattern(line)
                    if pattern:
                        patterns.append(pattern)

        except Exception as e:
            print(f"Warning: Could not parse .gitignore: {e}")
            return []

        return patterns

    def _convert_pattern(self, gitignore_pattern: str) -> str:
        """
        Convert a gitignore pattern to an indexer exclude pattern.

        Args:
            gitignore_pattern: Pattern from .gitignore file

        Returns:
            Converted pattern suitable for indexer, or empty string if invalid
        """
        pattern = gitignore_pattern.strip()

        if not pattern:
            return ""

        # Remove leading slash (absolute paths in git)
        if pattern.startswith('/'):
            pattern = pattern[1:]

        # Ensure directory patterns end with /
        if not pattern.endswith('/') and not pattern.endswith('*'):
            # Check if it's likely a directory (common patterns)
            if any(pattern.endswith(d) for d in [
                'modules', 'cache', 'dist', 'build', '_pycache__',
                'coverage', 'logs', '.git', '.venv', 'env'
            ]):
                pattern += '/'

        return pattern

    def get_exclude_patterns(self, include_defaults: bool = True) -> List[str]:
        """
        Get complete set of exclude patterns.

        Args:
            include_defaults: Whether to include default patterns

        Returns:
            Combined list of gitignore and default patterns
        """
        gitignore_patterns = self.parse_gitignore()

        if not include_defaults:
            return gitignore_patterns

        # Default patterns that should always be excluded
        defaults = self._get_default_patterns()

        # Combine and deduplicate
        all_patterns = list(dict.fromkeys(defaults + gitignore_patterns))

        return all_patterns

    def _get_default_patterns(self) -> List[str]:
        """Get default exclude patterns that should always apply."""
        return [
            # Core excludes (always needed)
            ".git/",
            ".claude-indexer/",
            ".claude/",

            # Python
            "*.pyc",
            "__pycache__/",
            "*.egg-info/",
            ".mypy_cache/",
            ".pytest_cache/",

            # Node.js
            "node_modules/",

            # Build outputs
            "dist/",
            "build/",

            # Logs
            "*.log",
            "logs/",

            # Databases
            "*.db",
            "*.sqlite3",

            # Memory system files
            "memory_guard_debug.txt",
            "memory_guard_debug_*.txt",
        ]


def get_patterns_for_project(project_path: Path | str) -> List[str]:
    """
    Convenience function to get exclude patterns for a project.

    Args:
        project_path: Path to project directory

    Returns:
        List of exclude patterns combining .gitignore and defaults
    """
    parser = GitignoreParser(Path(project_path))
    return parser.get_exclude_patterns(include_defaults=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: gitignore_parser.py <project_path>")
        sys.exit(1)

    project_path = Path(sys.argv[1])

    if not project_path.exists():
        print(f"Error: Project path not found: {project_path}")
        sys.exit(1)

    parser = GitignoreParser(project_path)
    patterns = parser.get_exclude_patterns()

    print(f"Found {len(patterns)} exclude patterns for {project_path}:")
    print()
    for pattern in patterns:
        print(f"  - {pattern}")
