#!/usr/bin/env python3
"""
Gitignore Pattern Detector for Automatic Exclude Configuration.

DEPRECATED: This module is maintained for backward compatibility.
New code should use exclusion_manager.py which provides:
- .gitignore support (this module)
- .claudeignore support (custom indexing exclusions)
- Binary file detection
- Enhanced universal defaults

Reads a project's .gitignore file and converts patterns to indexer-compatible
exclude patterns, ensuring build artifacts and generated files are never indexed.
"""

from pathlib import Path

# Import from new exclusion_manager for backward compatibility
try:
    from .exclusion_manager import (
        ExclusionManager,
        GitignoreParser,
        get_patterns_for_project,
    )
except ImportError:
    # When run as script, use absolute import
    from exclusion_manager import (
        ExclusionManager,
        GitignoreParser,
        get_patterns_for_project,
    )

# Re-export for backward compatibility
__all__ = ["GitignoreParser", "get_patterns_for_project", "ExclusionManager"]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: gitignore_parser.py <project_path>")
        print("Note: This script is deprecated. Use exclusion_manager.py instead.")
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
