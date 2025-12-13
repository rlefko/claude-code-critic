"""Git-aware change detection for incremental indexing.

This module provides GitChangeDetector which uses git to efficiently
detect file changes, with fallback to hash-based detection for non-git repos.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..indexer_logging import get_logger

if TYPE_CHECKING:
    from ..storage.file_cache import FileHashCache


@dataclass
class ChangeSet:
    """Represents detected file changes for incremental indexing.

    Attributes:
        added_files: List of newly added file paths
        modified_files: List of modified file paths
        deleted_files: List of deleted file relative paths
        renamed_files: List of (old_path, new_path) tuples for renames
        base_commit: The commit SHA used as base for comparison
        is_git_repo: Whether git-based detection was used
    """

    added_files: list[Path] = field(default_factory=list)
    modified_files: list[Path] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)  # relative paths
    renamed_files: list[tuple[str, str]] = field(
        default_factory=list
    )  # (old_path, new_path)
    base_commit: str | None = None
    is_git_repo: bool = True

    @property
    def has_changes(self) -> bool:
        """Check if any changes were detected."""
        return bool(
            self.added_files
            or self.modified_files
            or self.deleted_files
            or self.renamed_files
        )

    @property
    def total_files(self) -> int:
        """Total number of files affected."""
        return (
            len(self.added_files)
            + len(self.modified_files)
            + len(self.deleted_files)
            + len(self.renamed_files)
        )

    @property
    def files_to_index(self) -> list[Path]:
        """Get all files that need to be indexed (added + modified)."""
        return self.added_files + self.modified_files

    def summary(self) -> str:
        """Get a human-readable summary of changes."""
        parts = []
        if self.added_files:
            parts.append(f"{len(self.added_files)} added")
        if self.modified_files:
            parts.append(f"{len(self.modified_files)} modified")
        if self.deleted_files:
            parts.append(f"{len(self.deleted_files)} deleted")
        if self.renamed_files:
            parts.append(f"{len(self.renamed_files)} renamed")

        if not parts:
            return "No changes detected"

        source = "git" if self.is_git_repo else "hash comparison"
        return f"{', '.join(parts)} (via {source})"


class GitChangeDetector:
    """Git-aware change detection with hash-based fallback.

    Uses git to detect file changes efficiently, with fallback to
    FileHashCache for non-git repositories.

    Example:
        detector = GitChangeDetector(project_path)
        changes = detector.detect_changes(since_commit="HEAD~5")
        print(f"Files to index: {changes.files_to_index}")
    """

    def __init__(
        self,
        project_path: Path | str,
        file_hash_cache: "FileHashCache | None" = None,
    ):
        """Initialize the change detector.

        Args:
            project_path: Root directory of the project
            file_hash_cache: Optional FileHashCache for non-git fallback
        """
        self.project_path = Path(project_path).resolve()
        self.file_hash_cache = file_hash_cache
        self.logger = get_logger()
        self._is_git_repo: bool | None = None

    def is_git_repo(self) -> bool:
        """Check if the project directory is a git repository.

        Returns:
            True if the directory is within a git repository
        """
        if self._is_git_repo is not None:
            return self._is_git_repo

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                check=False,
            )
            self._is_git_repo = result.returncode == 0
        except (FileNotFoundError, OSError):
            self._is_git_repo = False

        return self._is_git_repo

    def get_current_commit(self) -> str | None:
        """Get the current HEAD commit SHA.

        Returns:
            The short commit SHA, or None if not a git repo
        """
        if not self.is_git_repo():
            return None

        try:
            result = self._run_git_command(["rev-parse", "--short", "HEAD"])
            return result.strip() if result else None
        except subprocess.CalledProcessError:
            return None

    def get_merge_base(self, branch: str) -> str | None:
        """Get the merge base between HEAD and a branch.

        Args:
            branch: The branch to compare against

        Returns:
            The merge base commit SHA, or None on error
        """
        if not self.is_git_repo():
            return None

        try:
            result = self._run_git_command(["merge-base", branch, "HEAD"])
            return result.strip() if result else None
        except subprocess.CalledProcessError:
            return None

    def detect_changes(
        self,
        since_commit: str | None = None,
        previous_state: dict | None = None,
    ) -> ChangeSet:
        """Detect file changes since a specific commit or state.

        Uses git if available, otherwise falls back to hash comparison.

        Args:
            since_commit: Git commit/ref to compare against (e.g., "HEAD~5", "abc123")
            previous_state: Optional previous state dict for hash fallback

        Returns:
            ChangeSet containing detected changes
        """
        if self.is_git_repo() and since_commit:
            self.logger.debug(f"Detecting changes via git since {since_commit}")
            return self._detect_via_git(["diff", "--name-status", "-M", since_commit])

        # Fallback to hash-based detection
        self.logger.debug("Detecting changes via hash comparison")
        return self._detect_via_hash(previous_state or {})

    def get_staged_files(self) -> ChangeSet:
        """Get staged files for pre-commit hook integration.

        Returns:
            ChangeSet containing staged file changes
        """
        if not self.is_git_repo():
            self.logger.warning("Not a git repo, cannot get staged files")
            return ChangeSet(is_git_repo=False)

        self.logger.debug("Detecting staged changes")
        return self._detect_via_git(["diff", "--cached", "--name-status", "-M", "HEAD"])

    def get_branch_diff(self, base_branch: str = "main") -> ChangeSet:
        """Get changes between current branch and base branch.

        Useful for PR-based indexing workflows.

        Args:
            base_branch: The base branch to diff against (default: "main")

        Returns:
            ChangeSet containing branch differences
        """
        if not self.is_git_repo():
            self.logger.warning("Not a git repo, cannot get branch diff")
            return ChangeSet(is_git_repo=False)

        # Get merge base for accurate 3-way diff
        merge_base = self.get_merge_base(base_branch)
        if not merge_base:
            self.logger.warning(f"Could not find merge base with {base_branch}")
            return ChangeSet(is_git_repo=True, base_commit=base_branch)

        self.logger.debug(
            f"Detecting branch diff against {base_branch} (base: {merge_base})"
        )
        return self._detect_via_git(
            ["diff", "--name-status", "-M", f"{merge_base}..HEAD"]
        )

    def get_commit_range(self, from_ref: str, to_ref: str = "HEAD") -> ChangeSet:
        """Get changes between two commits.

        Args:
            from_ref: Starting commit/ref
            to_ref: Ending commit/ref (default: HEAD)

        Returns:
            ChangeSet containing changes in the range
        """
        if not self.is_git_repo():
            self.logger.warning("Not a git repo, cannot get commit range")
            return ChangeSet(is_git_repo=False)

        self.logger.debug(f"Detecting changes from {from_ref} to {to_ref}")
        return self._detect_via_git(
            ["diff", "--name-status", "-M", f"{from_ref}..{to_ref}"]
        )

    def get_uncommitted_changes(self) -> ChangeSet:
        """Get all uncommitted changes (staged + unstaged).

        Returns:
            ChangeSet containing all uncommitted changes
        """
        if not self.is_git_repo():
            self.logger.warning("Not a git repo, cannot get uncommitted changes")
            return ChangeSet(is_git_repo=False)

        self.logger.debug("Detecting all uncommitted changes")
        return self._detect_via_git(["diff", "--name-status", "-M", "HEAD"])

    def _detect_via_git(self, git_args: list[str]) -> ChangeSet:
        """Detect changes using git command.

        Args:
            git_args: Arguments to pass to git (e.g., ["diff", "--name-status", "HEAD"])

        Returns:
            ChangeSet parsed from git output
        """
        try:
            output = self._run_git_command(git_args)
            return self._parse_git_status(output)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git command failed: {e}")
            return ChangeSet(is_git_repo=True)

    def _parse_git_status(self, output: str) -> ChangeSet:
        """Parse git diff --name-status output.

        Format examples:
            A\tfile.py          # Added
            M\tfile.py          # Modified
            D\tfile.py          # Deleted
            R100\told.py\tnew.py  # Renamed (100% similarity)
            R095\told.py\tnew.py  # Renamed (95% similarity)

        Args:
            output: Raw output from git diff --name-status

        Returns:
            Parsed ChangeSet
        """
        added_files: list[Path] = []
        modified_files: list[Path] = []
        deleted_files: list[str] = []
        renamed_files: list[tuple[str, str]] = []

        for line in output.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status = parts[0]
            file_path = parts[-1]  # Last part is always the (new) file path

            if status == "A":
                # Added file
                full_path = self.project_path / file_path
                if full_path.exists():
                    added_files.append(full_path)
            elif status == "M":
                # Modified file
                full_path = self.project_path / file_path
                if full_path.exists():
                    modified_files.append(full_path)
            elif status == "D":
                # Deleted file
                deleted_files.append(file_path)
            elif status.startswith("R"):
                # Renamed file (R followed by similarity percentage)
                if len(parts) >= 3:
                    old_path = parts[1]
                    new_path = parts[2]
                    renamed_files.append((old_path, new_path))
                    # Also add the new path to modified files for re-indexing
                    full_new_path = self.project_path / new_path
                    if full_new_path.exists():
                        modified_files.append(full_new_path)
            elif status.startswith("C"):
                # Copied file - treat as added
                full_path = self.project_path / file_path
                if full_path.exists():
                    added_files.append(full_path)
            else:
                # Unknown status, treat as modified
                full_path = self.project_path / file_path
                if full_path.exists():
                    modified_files.append(full_path)

        return ChangeSet(
            added_files=added_files,
            modified_files=modified_files,
            deleted_files=deleted_files,
            renamed_files=renamed_files,
            base_commit=self.get_current_commit(),
            is_git_repo=True,
        )

    def _detect_via_hash(self, previous_state: dict) -> ChangeSet:
        """Detect changes using file hash comparison.

        Falls back to this when not in a git repository.

        Args:
            previous_state: Dict mapping relative paths to file info
                          (with "hash" key for content hash)

        Returns:
            ChangeSet based on hash comparison
        """
        from ..storage.file_cache import FileHashCache

        added_files: list[Path] = []
        modified_files: list[Path] = []
        deleted_files: list[str] = []

        # Get all current files
        current_files = self._find_all_files()
        current_paths = set()

        for file_path in current_files:
            try:
                rel_path = str(file_path.relative_to(self.project_path))
                current_paths.add(rel_path)

                if rel_path not in previous_state:
                    # New file
                    added_files.append(file_path)
                else:
                    # Check if modified
                    current_hash = FileHashCache.compute_file_hash(file_path)
                    previous_hash = previous_state.get(rel_path, {}).get("hash", "")

                    if current_hash != previous_hash:
                        modified_files.append(file_path)
            except ValueError:
                continue

        # Find deleted files
        previous_paths = {
            k for k in previous_state if not k.startswith("_")
        }  # Exclude metadata keys
        deleted = previous_paths - current_paths
        deleted_files.extend(deleted)

        return ChangeSet(
            added_files=added_files,
            modified_files=modified_files,
            deleted_files=deleted_files,
            renamed_files=[],  # Cannot detect renames without git
            base_commit=None,
            is_git_repo=False,
        )

    def _find_all_files(self) -> list[Path]:
        """Find all indexable files in the project.

        Returns:
            List of file paths (uses git ls-files if available)
        """
        if self.is_git_repo():
            try:
                output = self._run_git_command(["ls-files"])
                files = []
                for line in output.strip().split("\n"):
                    if line:
                        file_path = self.project_path / line
                        if file_path.exists() and file_path.is_file():
                            files.append(file_path)
                return files
            except subprocess.CalledProcessError:
                pass

        # Fallback: walk directory
        files = []
        for file_path in self.project_path.rglob("*"):
            if file_path.is_file() and not self._should_skip(file_path):
                files.append(file_path)
        return files

    def _should_skip(self, file_path: Path) -> bool:
        """Check if file should be skipped during directory walk.

        Args:
            file_path: Path to check

        Returns:
            True if file should be skipped
        """
        # Skip common non-indexable patterns
        skip_patterns = [
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            "node_modules",
            ".index_cache",
            ".pytest_cache",
            ".mypy_cache",
        ]

        parts = file_path.parts
        return any(pattern in parts for pattern in skip_patterns)

    def _run_git_command(self, args: list[str]) -> str:
        """Run a git command and return stdout.

        Args:
            args: Git command arguments (without "git")

        Returns:
            Command stdout as string

        Raises:
            subprocess.CalledProcessError: If command fails
        """
        result = subprocess.run(
            ["git"] + args,
            cwd=self.project_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
