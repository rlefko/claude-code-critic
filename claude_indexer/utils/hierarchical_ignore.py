"""Hierarchical .claudeignore manager with global + project pattern merging.

This module provides a multi-level ignore system that loads patterns from:
1. Universal defaults (UNIVERSAL_EXCLUDES - binaries, OS artifacts, etc.)
2. Global .claudeignore (~/.claude-indexer/.claudeignore)
3. Project .claudeignore (.claudeignore in project root)

Later patterns can negate earlier ones using gitignore's ! syntax.

Example usage:
    manager = HierarchicalIgnoreManager(project_root).load()

    if manager.should_ignore("src/secret.key"):
        print("File should be ignored")

    reason = manager.get_ignore_reason("node_modules/foo.js")
    # Returns: "Matched pattern: node_modules/"
"""

import logging
import sys
from pathlib import Path

from .claudeignore_parser import ClaudeIgnoreParser

logger = logging.getLogger(__name__)

# Import UNIVERSAL_EXCLUDES from the existing exclusion_manager
# This is in the root utils/ directory, not claude_indexer/utils/
try:
    # Try relative import first
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    from utils.exclusion_manager import UNIVERSAL_EXCLUDES
except ImportError:
    # Fallback: define a subset of universal excludes
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
        "__pycache__/",
        ".venv/",
        "venv/",
        # Node.js
        "node_modules/",
        # Build outputs
        "dist/",
        "build/",
        # Binaries
        "*.exe",
        "*.dll",
        "*.so",
        # Package locks
        "package-lock.json",
        "yarn.lock",
        "poetry.lock",
        # Logs
        "*.log",
        "logs/",
    ]


class HierarchicalIgnoreManager:
    """Multi-level .claudeignore with precedence.

    Precedence (patterns loaded in order):
    1. Universal defaults (UNIVERSAL_EXCLUDES)
    2. Global patterns (~/.claude-indexer/.claudeignore)
    3. Project patterns (.claudeignore in project root)

    Later patterns can negate earlier ones with !

    Attributes:
        project_root: The project root directory.
        global_ignore_path: Path to global .claudeignore.
        project_ignore_path: Path to project .claudeignore.
    """

    GLOBAL_IGNORE = Path.home() / ".claude-indexer" / ".claudeignore"

    def __init__(self, project_root: Path | str):
        """Initialize the hierarchical ignore manager.

        Args:
            project_root: Path to the project root directory.
        """
        self.project_root = Path(project_root).resolve()
        self.global_ignore_path = self.GLOBAL_IGNORE
        self.project_ignore_path = self.project_root / ".claudeignore"

        self._parser = ClaudeIgnoreParser(self.project_root)
        self._loaded = False
        self._sources: dict[str, int] = {}  # Track pattern counts by source

    def load(self) -> "HierarchicalIgnoreManager":
        """Load patterns from all sources with proper precedence.

        Patterns are loaded in order:
        1. Universal defaults
        2. Global .claudeignore (if exists)
        3. Project .claudeignore (if exists)

        Returns:
            Self for method chaining.
        """
        self._parser.clear()
        self._sources.clear()

        # Layer 1: Universal defaults
        universal_count = len(UNIVERSAL_EXCLUDES)
        self._parser.add_patterns(UNIVERSAL_EXCLUDES)
        self._sources["universal"] = universal_count
        logger.debug(f"Loaded {universal_count} universal exclude patterns")

        # Layer 2: Global .claudeignore
        if self.global_ignore_path.exists():
            global_count = self._parser.load_file(self.global_ignore_path)
            self._sources["global"] = global_count
            logger.debug(f"Loaded {global_count} patterns from global .claudeignore")
        else:
            self._sources["global"] = 0
            logger.debug("No global .claudeignore found")

        # Layer 3: Project .claudeignore
        if self.project_ignore_path.exists():
            project_count = self._parser.load_file(self.project_ignore_path)
            self._sources["project"] = project_count
            logger.debug(f"Loaded {project_count} patterns from project .claudeignore")
        else:
            self._sources["project"] = 0
            logger.debug("No project .claudeignore found")

        self._loaded = True
        return self

    def should_ignore(self, path: Path | str) -> bool:
        """Check if a path should be ignored.

        Args:
            path: Path to check (can be absolute or relative to project root).

        Returns:
            True if the path should be ignored.
        """
        if not self._loaded:
            self.load()

        return self._parser.matches(path)

    def get_ignore_reason(self, path: Path | str) -> str | None:
        """Get the reason why a path is ignored (for debugging).

        Args:
            path: Path to check.

        Returns:
            A string describing why the path is ignored, or None if not ignored.
        """
        if not self._loaded:
            self.load()

        pattern = self._parser.get_matching_pattern(path)
        if pattern:
            source = self._get_pattern_source(pattern)
            return f"Matched pattern '{pattern}' from {source}"
        return None

    def _get_pattern_source(self, pattern: str) -> str:
        """Determine which source a pattern came from.

        Args:
            pattern: The pattern to find the source for.

        Returns:
            A string describing the source (universal, global, or project).
        """
        if pattern in UNIVERSAL_EXCLUDES:
            return "universal defaults"

        # Check global file
        if self.global_ignore_path.exists():
            try:
                with open(self.global_ignore_path) as f:
                    if pattern in f.read():
                        return f"global ({self.global_ignore_path})"
            except OSError:
                pass

        # Must be from project
        return f"project ({self.project_ignore_path})"

    def get_stats(self) -> dict[str, int | bool | str]:
        """Get statistics about loaded patterns.

        Returns:
            Dictionary with pattern counts and source information.
        """
        if not self._loaded:
            self.load()

        return {
            "total_patterns": self._parser.pattern_count,
            "universal_patterns": self._sources.get("universal", 0),
            "global_patterns": self._sources.get("global", 0),
            "project_patterns": self._sources.get("project", 0),
            "global_ignore_exists": self.global_ignore_path.exists(),
            "project_ignore_exists": self.project_ignore_path.exists(),
            "project_root": str(self.project_root),
        }

    def filter_paths(self, paths: list[Path | str]) -> list[Path]:
        """Filter a list of paths, returning only those NOT ignored.

        Args:
            paths: List of paths to filter.

        Returns:
            List of paths that should be included (not ignored).
        """
        if not self._loaded:
            self.load()

        return self._parser.filter_paths(paths)

    @property
    def patterns(self) -> list[str]:
        """Return all loaded patterns."""
        if not self._loaded:
            self.load()
        return self._parser.patterns

    @property
    def is_loaded(self) -> bool:
        """Return whether patterns have been loaded."""
        return self._loaded


def create_default_claudeignore(
    path: Path | str, include_secrets: bool = True, include_ml: bool = True
) -> Path:
    """Create a default .claudeignore file at the specified path.

    Args:
        path: Directory where .claudeignore should be created.
        include_secrets: Include patterns for secrets/credentials.
        include_ml: Include patterns for AI/ML artifacts.

    Returns:
        Path to the created file.
    """
    path = Path(path)
    if path.is_dir():
        path = path / ".claudeignore"

    content = """# .claudeignore - Custom Exclusions for Code Indexing
#
# This file works like .gitignore but specifically controls what gets indexed
# into semantic memory. Patterns here are IN ADDITION to .gitignore patterns.
#
# Syntax is identical to .gitignore:
# - Lines starting with # are comments
# - * matches any string except /
# - ** matches any string including /
# - ! negates a pattern (includes a previously excluded file)
# - / at end denotes a directory
# - / at start makes pattern relative to project root

"""

    if include_secrets:
        content += """# ============================================================================
# Secrets and Credentials (CRITICAL - NEVER INDEX)
# ============================================================================

# Environment files
.env
.env.*
!.env.example
!.env.template

# API keys and credentials
**/credentials.json
**/secrets.json
**/serviceAccountKey.json
**/*.pem
**/*.key
**/*secret*
**/*credential*
**/auth.json
**/.netrc

"""

    if include_ml:
        content += """# ============================================================================
# AI/ML Artifacts (Large Files)
# ============================================================================

# Model files
*.h5
*.pkl
*.joblib
*.onnx
*.pt
*.pth
*.safetensors
*.ckpt
*.bin

# Datasets
*.csv
*.parquet
*.arrow
*.feather

"""

    content += """# ============================================================================
# Personal Development Files
# ============================================================================

# Personal notes and TODOs
*-notes.md
*-notes.txt
TODO-*.md
NOTES.md
scratch.*

# ============================================================================
# Test and Debug Artifacts
# ============================================================================

# Test results
test-results/
test-output/
.coverage
htmlcov/
coverage/
junit.xml

# Debug output
debug-*.log
*.dump
*.prof
*.trace

# ============================================================================
# Your Custom Patterns Below
# ============================================================================

"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return path
