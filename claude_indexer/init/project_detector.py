"""Enhanced project type detection for initialization."""

import hashlib
import json
import re
import secrets
import subprocess
from pathlib import Path
from typing import ClassVar

from ..indexer_logging import get_logger
from .types import ProjectType

logger = get_logger()


class ProjectDetector:
    """Enhanced project type and language detection."""

    # Markers used for project root detection (in priority order)
    PROJECT_ROOT_MARKERS: ClassVar[list[str]] = [
        ".claude-indexer",  # Already initialized project (highest priority)
        ".git",
        "package.json",
        "pyproject.toml",
        "setup.py",
        "Cargo.toml",
        "go.mod",
        "Makefile",
        ".claude",  # Claude Code config directory
    ]

    @staticmethod
    def find_project_root(start_path: Path | None = None) -> Path | None:
        """Find project root by walking up from start_path.

        Searches for project markers starting from the given path and
        walking up the directory tree until a marker is found or the
        filesystem root is reached.

        This is a static method for convenience - it doesn't require
        instantiating ProjectDetector.

        Args:
            start_path: Starting directory (defaults to CWD)

        Returns:
            Path to project root, or None if not found

        Example:
            root = ProjectDetector.find_project_root()
            if root:
                detector = ProjectDetector(root)
                project_type = detector.detect_project_type()
        """
        current = (start_path or Path.cwd()).resolve()

        # Walk up to root
        while current != current.parent:
            for marker in ProjectDetector.PROJECT_ROOT_MARKERS:
                marker_path = current / marker
                if marker_path.exists():
                    return current
            current = current.parent

        # Check root directory as well
        for marker in ProjectDetector.PROJECT_ROOT_MARKERS:
            marker_path = current / marker
            if marker_path.exists():
                return current

        return None

    @staticmethod
    def detect_from_cwd() -> Path:
        """Find project root from CWD or use CWD as fallback.

        This method never returns None - if no project root is found,
        it falls back to using the current working directory.

        Returns:
            Path to project root (never None - uses CWD as fallback)
        """
        root = ProjectDetector.find_project_root()
        return root if root else Path.cwd().resolve()

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path).resolve()
        self._file_cache: set[Path] | None = None

    def _get_project_files(self) -> set[Path]:
        """Get all project files (cached)."""
        if self._file_cache is None:
            self._file_cache = set()
            try:
                for f in self.project_path.rglob("*"):
                    # Skip common large directories
                    parts = f.parts
                    if any(
                        p in parts
                        for p in [
                            "node_modules",
                            ".git",
                            ".venv",
                            "venv",
                            "__pycache__",
                            "dist",
                            "build",
                        ]
                    ):
                        continue
                    if f.is_file():
                        self._file_cache.add(f)
            except PermissionError:
                pass
        return self._file_cache

    def detect_project_type(self) -> ProjectType:
        """Detect project type based on config files and structure.

        Priority order:
        1. next.config.js/ts/mjs -> NEXTJS
        2. vue.config.js / vite.config with vue / .vue files -> VUE
        3. tsconfig.json with React -> REACT
        4. tsconfig.json -> TYPESCRIPT
        5. package.json (no TS) -> JAVASCRIPT
        6. pyproject.toml / setup.py / requirements.txt -> PYTHON
        7. GENERIC
        """
        # Check for Next.js
        if self._has_file("next.config.js", "next.config.ts", "next.config.mjs"):
            logger.debug("Detected Next.js project")
            return ProjectType.NEXTJS

        # Check for Vue
        if self._has_file("vue.config.js") or self._has_vue_files():
            logger.debug("Detected Vue project")
            return ProjectType.VUE

        # Check for React (tsconfig with react)
        if self._has_file("tsconfig.json") and self._is_react_project():
            logger.debug("Detected React/TypeScript project")
            return ProjectType.REACT

        # Check for TypeScript
        if self._has_file("tsconfig.json"):
            logger.debug("Detected TypeScript project")
            return ProjectType.TYPESCRIPT

        # Check for JavaScript (package.json)
        if self._has_file("package.json"):
            logger.debug("Detected JavaScript project")
            return ProjectType.JAVASCRIPT

        # Check for Python
        if self._has_file(
            "pyproject.toml", "setup.py", "requirements.txt", "Pipfile", "poetry.lock"
        ):
            logger.debug("Detected Python project")
            return ProjectType.PYTHON

        # Check by file extensions as fallback
        files = self._get_project_files()
        has_py = any(f.suffix == ".py" for f in files)
        has_js = any(f.suffix in {".js", ".ts", ".jsx", ".tsx"} for f in files)

        if has_py and not has_js:
            return ProjectType.PYTHON
        if has_js and not has_py:
            return ProjectType.JAVASCRIPT

        return ProjectType.GENERIC

    def _has_file(self, *filenames: str) -> bool:
        """Check if any of the given files exist in project root."""
        return any((self.project_path / f).exists() for f in filenames)

    def _has_vue_files(self) -> bool:
        """Check if project has .vue files."""
        files = self._get_project_files()
        return any(f.suffix == ".vue" for f in files)

    def _is_react_project(self) -> bool:
        """Check if project uses React (via package.json)."""
        package_json = self.project_path / "package.json"
        if not package_json.exists():
            return False

        try:
            with open(package_json) as f:
                data = json.load(f)
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            return "react" in deps or "react-dom" in deps
        except (OSError, json.JSONDecodeError):
            return False

    def detect_languages(self) -> list[str]:
        """Detect all languages used in the project."""
        languages = set()
        files = self._get_project_files()

        extension_map = {
            ".py": "python",
            ".pyi": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".vue": "vue",
            ".html": "html",
            ".htm": "html",
            ".css": "css",
            ".scss": "css",
            ".sass": "css",
            ".less": "css",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".mdx": "markdown",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
        }

        for f in files:
            lang = extension_map.get(f.suffix.lower())
            if lang:
                languages.add(lang)

        return sorted(languages)

    def derive_collection_name(
        self,
        custom_name: str | None = None,
        prefix: str | None = None,
        include_hash: bool = False,
    ) -> str:
        """Derive collection name from project directory name.

        Args:
            custom_name: Optional custom name to use instead of deriving.
            prefix: Optional prefix for multi-tenancy (e.g., "claude").
            include_hash: If True, append 6-char uniqueness hash.

        Returns:
            Sanitized collection name suitable for Qdrant.
            Format: {prefix}_{name}_{hash} or just {name} depending on args.
        """
        name = custom_name or self.project_path.name

        # Sanitize: lowercase, replace spaces/special chars with hyphens
        name = name.lower()
        name = re.sub(r"[^a-z0-9-]", "-", name)
        name = re.sub(r"-+", "-", name)  # Collapse multiple hyphens
        name = name.strip("-")

        # Ensure it's not empty
        if not name:
            name = "project"

        # Build final collection name
        parts = []
        if prefix:
            # Sanitize prefix the same way
            prefix = prefix.lower()
            prefix = re.sub(r"[^a-z0-9-]", "-", prefix)
            prefix = re.sub(r"-+", "-", prefix).strip("-")
            if prefix:
                parts.append(prefix)

        parts.append(name)

        if include_hash:
            hash_suffix = self.get_collection_hash()
            parts.append(hash_suffix)

        # Use underscore as separator for readability
        return "_".join(parts)

    def is_git_repository(self) -> bool:
        """Check if project is a git repository."""
        git_dir = self.project_path / ".git"
        return git_dir.exists() and git_dir.is_dir()

    def get_git_remote_url(self) -> str | None:
        """Get the git remote origin URL.

        Returns:
            Remote URL string or None if not available.
        """
        if not self.is_git_repository():
            return None

        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"Could not get git remote URL: {e}")
        return None

    def get_collection_hash(self) -> str:
        """Get 6-char hash for collection uniqueness.

        Uses git remote URL hash if available, otherwise generates random.

        Returns:
            6-character hexadecimal string.
        """
        remote_url = self.get_git_remote_url()
        if remote_url:
            # Normalize URL (remove .git suffix, normalize case for github)
            normalized = remote_url.lower().rstrip("/")
            if normalized.endswith(".git"):
                normalized = normalized[:-4]
            return hashlib.sha256(normalized.encode()).hexdigest()[:6]
        # Fallback to random hash for non-git repos
        return secrets.token_hex(3)

    def get_project_name(self) -> str:
        """Get the project name (directory name)."""
        return self.project_path.name

    def get_project_info(self) -> dict:
        """Get comprehensive project information."""
        return {
            "name": self.get_project_name(),
            "path": str(self.project_path),
            "type": self.detect_project_type().value,
            "languages": self.detect_languages(),
            "is_git": self.is_git_repository(),
        }
