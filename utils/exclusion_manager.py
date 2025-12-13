#!/usr/bin/env python3
"""
Multi-Layer Exclusion Manager for Semantic Code Indexing.

Provides comprehensive file exclusion through multiple layers:
1. Universal defaults (binaries, OS artifacts, media)
2. .gitignore patterns (project version control ignores)
3. .claudeignore patterns (indexing-specific custom ignores)
4. Binary detection (magic numbers, executable bits)

Usage:
    manager = ExclusionManager(project_root)
    patterns = manager.get_all_patterns()
    if manager.should_exclude(file_path):
        skip_indexing()
"""

import os
from pathlib import Path

# Universal exclusion patterns (always applied)
UNIVERSAL_EXCLUDES = [
    # Core system directories
    ".git/",
    ".claude-indexer/",
    ".claude/",
    ".svn/",
    ".hg/",
    # Python
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "__pycache__/",
    "*.egg-info/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".tox/",
    ".venv/",
    "venv/",
    "env/",
    # Node.js
    "node_modules/",
    ".npm/",
    ".yarn/",
    # Build outputs
    "dist/",
    "build/",
    "out/",
    "target/",  # Rust/Java
    # Binaries and compiled code
    "*.exe",
    "*.dll",
    "*.so",
    "*.dylib",
    "*.a",
    "*.lib",
    "*.o",
    "*.obj",
    "*.class",
    "*.bin",
    # Archives
    "*.zip",
    "*.tar",
    "*.gz",
    "*.7z",
    "*.rar",
    "*.bz2",
    "*.xz",
    "*.tgz",
    # OS artifacts
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".Spotlight-V100/",
    ".Trashes/",
    ".fseventsd/",
    "~$*",  # Windows temp files
    # Package lock files (large, auto-generated)
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
    "Pipfile.lock",
    # Media files
    "*.mp4",
    "*.avi",
    "*.mov",
    "*.mkv",
    "*.mp3",
    "*.wav",
    "*.flac",
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.gif",
    "*.ico",
    "*.bmp",
    "*.webp",
    "*.pdf",
    "*.doc",
    "*.docx",
    "*.ppt",
    "*.pptx",
    "*.xls",
    "*.xlsx",
    # Database files
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    # Logs
    "*.log",
    "logs/",
    # Memory guard artifacts
    "memory_guard_debug.txt",
    "memory_guard_debug_*.txt",
    # IDE and editor
    ".idea/",
    ".vscode/",
    "*.swp",
    "*.swo",
    "*~",
]

# Binary file extensions
BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".a",
    ".lib",
    ".o",
    ".obj",
    ".class",
    ".pyc",
    ".pyd",
    ".pyo",
    ".bin",
    ".elf",
}

# Magic number signatures for binary files
BINARY_MAGIC_SIGNATURES = [
    b"\x7fELF",  # ELF (Linux executables)
    b"MZ",  # PE (Windows executables)
    b"\xfe\xed\xfa\xce",  # Mach-O 32-bit (macOS)
    b"\xfe\xed\xfa\xcf",  # Mach-O 64-bit (macOS)
    b"\xca\xfe\xba\xbe",  # Universal binary (macOS)
    b"\xcf\xfa\xed\xfe",  # Mach-O reverse byte order
]


class ExclusionManager:
    """Manage multi-layer file exclusion patterns for code indexing."""

    def __init__(self, project_root: Path | str):
        """
        Initialize exclusion manager for a project.

        Args:
            project_root: Path to project directory
        """
        self.project_root = Path(project_root).resolve()
        self.gitignore_path = self.project_root / ".gitignore"
        self.claudeignore_path = self.project_root / ".claudeignore"

    def get_all_patterns(self) -> list[str]:
        """
        Get combined exclusion patterns from all layers.

        Returns:
            List of exclusion patterns (deduplicated, order preserved)
        """
        patterns = []

        # Layer 1: Universal defaults
        patterns.extend(UNIVERSAL_EXCLUDES)

        # Layer 2: .gitignore patterns
        patterns.extend(self._parse_ignore_file(self.gitignore_path))

        # Layer 3: .claudeignore patterns
        patterns.extend(self._parse_ignore_file(self.claudeignore_path))

        # Deduplicate while preserving order
        return list(dict.fromkeys(patterns))

    def should_exclude(self, file_path: Path | str) -> bool:
        """
        Check if a file should be excluded from indexing.

        Args:
            file_path: Path to file (can be relative or absolute)

        Returns:
            True if file should be excluded, False otherwise
        """
        file_path = Path(file_path)

        # Make absolute if relative
        if not file_path.is_absolute():
            file_path = self.project_root / file_path

        # Check if it's a binary file
        if file_path.exists() and self.is_binary_file(file_path):
            return True

        # Check against pattern list
        patterns = self.get_all_patterns()
        relative_path = str(file_path.relative_to(self.project_root))

        for pattern in patterns:
            if self._matches_pattern(relative_path, pattern):
                return True

        return False

    def is_binary_file(self, file_path: Path) -> bool:
        """
        Detect if a file is binary/executable.

        Uses multiple detection methods:
        1. File extension
        2. Executable permission bit
        3. Magic number signatures

        Args:
            file_path: Path to file

        Returns:
            True if file is binary, False otherwise
        """
        if not file_path.exists() or not file_path.is_file():
            return False

        # Check extension
        if file_path.suffix in BINARY_EXTENSIONS:
            return True

        # Check if file is executable (Unix-like systems)
        if not file_path.suffix and os.access(file_path, os.X_OK):
            # Executable without extension - likely binary
            return True

        # Check magic numbers (first 4 bytes)
        try:
            with open(file_path, "rb") as f:
                magic = f.read(4)
                for signature in BINARY_MAGIC_SIGNATURES:
                    if magic.startswith(signature):
                        return True
        except OSError:
            # If we can't read it, assume it might be binary
            return True

        return False

    def _parse_ignore_file(self, ignore_path: Path) -> list[str]:
        """
        Parse .gitignore or .claudeignore file.

        Args:
            ignore_path: Path to ignore file

        Returns:
            List of patterns from the file
        """
        if not ignore_path.exists():
            return []

        patterns = []

        try:
            with open(ignore_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue

                    # Skip negation patterns (not supported in simple exclude)
                    if line.startswith("!"):
                        continue

                    # Convert pattern
                    pattern = self._convert_pattern(line)
                    if pattern:
                        patterns.append(pattern)

        except Exception as e:
            print(f"Warning: Could not parse {ignore_path}: {e}")
            return []

        return patterns

    def _convert_pattern(self, pattern: str) -> str:
        """
        Convert gitignore-style pattern to indexer pattern.

        Args:
            pattern: Pattern from ignore file

        Returns:
            Converted pattern suitable for indexer
        """
        pattern = pattern.strip()

        if not pattern:
            return ""

        # Remove leading slash (absolute paths in git)
        if pattern.startswith("/"):
            pattern = pattern[1:]

        # Ensure directory patterns end with /
        if not pattern.endswith("/") and not pattern.endswith("*"):
            # Check if it's likely a directory (common patterns)
            if any(
                pattern.endswith(d)
                for d in [
                    "modules",
                    "cache",
                    "dist",
                    "build",
                    "_pycache__",
                    "coverage",
                    "logs",
                    ".git",
                    ".venv",
                    "env",
                    "target",
                    "node_modules",
                    "__pycache__",
                    "htmlcov",
                ]
            ):
                pattern += "/"

        return pattern

    def _matches_pattern(self, path: str, pattern: str) -> bool:
        """
        Check if a path matches an exclusion pattern.

        Args:
            path: File path (relative to project root)
            pattern: Exclusion pattern

        Returns:
            True if path matches pattern
        """
        # Simple pattern matching (can be enhanced with fnmatch/pathlib)
        from fnmatch import fnmatch

        # Directory pattern
        if pattern.endswith("/"):
            return path.startswith(pattern.rstrip("/")) or fnmatch(path, pattern + "*")

        # File pattern
        return fnmatch(path, pattern) or fnmatch(os.path.basename(path), pattern)


# Backward compatibility functions


def get_patterns_for_project(project_path: Path | str) -> list[str]:
    """
    Convenience function to get all exclusion patterns for a project.

    Backward compatible with gitignore_parser.py interface.

    Args:
        project_path: Path to project directory

    Returns:
        List of exclusion patterns
    """
    manager = ExclusionManager(Path(project_path))
    return manager.get_all_patterns()


class GitignoreParser:
    """Backward compatibility wrapper for old GitignoreParser interface."""

    def __init__(self, project_root: Path):
        self.manager = ExclusionManager(project_root)
        self.project_root = Path(project_root).resolve()
        self.gitignore_path = self.project_root / ".gitignore"

    def parse_gitignore(self) -> list[str]:
        """Parse .gitignore and return list of exclude patterns."""
        return self.manager._parse_ignore_file(self.manager.gitignore_path)

    def get_exclude_patterns(self, include_defaults: bool = True) -> list[str]:
        """Get complete set of exclude patterns."""
        if not include_defaults:
            return self.parse_gitignore()
        return self.manager.get_all_patterns()

    def _get_default_patterns(self) -> list[str]:
        """Get default exclude patterns that should always apply."""
        return UNIVERSAL_EXCLUDES

    def _convert_pattern(self, gitignore_pattern: str) -> str:
        """Convert a gitignore pattern to an indexer exclude pattern."""
        return self.manager._convert_pattern(gitignore_pattern)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: exclusion_manager.py <project_path>")
        sys.exit(1)

    project_path = Path(sys.argv[1])

    if not project_path.exists():
        print(f"Error: Project path not found: {project_path}")
        sys.exit(1)

    manager = ExclusionManager(project_path)
    patterns = manager.get_all_patterns()

    print(f"Found {len(patterns)} exclusion patterns for {project_path}:")
    print()

    # Group by source
    gitignore_patterns = manager._parse_ignore_file(manager.gitignore_path)
    claudeignore_patterns = manager._parse_ignore_file(manager.claudeignore_path)

    print(f"Universal defaults: {len(UNIVERSAL_EXCLUDES)}")
    print(f".gitignore patterns: {len(gitignore_patterns)}")
    print(f".claudeignore patterns: {len(claudeignore_patterns)}")
    print()
    print("Combined patterns:")
    for pattern in patterns:
        print(f"  - {pattern}")
