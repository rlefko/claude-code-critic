"""Git diff collector for change-aware UI analysis.

This module provides functionality to collect changed files and line ranges
from git, enabling diff-aware analysis that only flags issues in new or
modified code.
"""

import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class FileChange:
    """Represents a changed file with line-level granularity.

    Tracks which lines were added or deleted to enable precise
    "new vs baseline" issue classification.
    """

    file_path: Path
    change_type: str  # 'added', 'modified', 'deleted', 'renamed'
    added_lines: list[tuple[int, int]] = field(
        default_factory=list
    )  # (start, end) ranges
    deleted_lines: list[tuple[int, int]] = field(default_factory=list)
    old_path: Path | None = None  # For renames

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": str(self.file_path),
            "change_type": self.change_type,
            "added_lines": self.added_lines,
            "deleted_lines": self.deleted_lines,
            "old_path": str(self.old_path) if self.old_path else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileChange":
        """Create from dictionary."""
        return cls(
            file_path=Path(data["file_path"]),
            change_type=data["change_type"],
            added_lines=[tuple(r) for r in data.get("added_lines", [])],
            deleted_lines=[tuple(r) for r in data.get("deleted_lines", [])],
            old_path=Path(data["old_path"]) if data.get("old_path") else None,
        )

    def contains_line(self, line_number: int) -> bool:
        """Check if a line number is within the added line ranges.

        Args:
            line_number: The line number to check.

        Returns:
            True if the line is within any added range.
        """
        return any(start <= line_number <= end for start, end in self.added_lines)

    def is_ui_file(self, extensions: list[str] | None = None) -> bool:
        """Check if this is a UI-related file.

        Args:
            extensions: List of UI file extensions to check against.

        Returns:
            True if the file has a UI-related extension.
        """
        if extensions is None:
            extensions = GitDiffCollector.UI_EXTENSIONS
        return self.file_path.suffix.lower() in extensions


@dataclass
class DiffResult:
    """Complete diff result for a git operation.

    Contains all file changes and metadata about the diff.
    """

    changes: list[FileChange] = field(default_factory=list)
    base_ref: str = "HEAD"
    target_ref: str = ""  # Empty for working tree
    computed_at: str = ""

    def __post_init__(self):
        """Set computed_at timestamp if not provided."""
        if not self.computed_at:
            self.computed_at = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "changes": [c.to_dict() for c in self.changes],
            "base_ref": self.base_ref,
            "target_ref": self.target_ref,
            "computed_at": self.computed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiffResult":
        """Create from dictionary."""
        return cls(
            changes=[FileChange.from_dict(c) for c in data.get("changes", [])],
            base_ref=data.get("base_ref", "HEAD"),
            target_ref=data.get("target_ref", ""),
            computed_at=data.get("computed_at", ""),
        )

    def get_ui_files(self, extensions: list[str] | None = None) -> list[FileChange]:
        """Filter to UI-related files.

        Args:
            extensions: List of extensions to filter by.

        Returns:
            List of FileChange objects for UI files only.
        """
        return [c for c in self.changes if c.is_ui_file(extensions)]

    def get_added_files(self) -> list[FileChange]:
        """Get only newly added files."""
        return [c for c in self.changes if c.change_type == "added"]

    def get_modified_files(self) -> list[FileChange]:
        """Get only modified files."""
        return [c for c in self.changes if c.change_type == "modified"]

    def get_deleted_files(self) -> list[FileChange]:
        """Get only deleted files."""
        return [c for c in self.changes if c.change_type == "deleted"]

    @property
    def file_count(self) -> int:
        """Total number of changed files."""
        return len(self.changes)

    @property
    def ui_file_count(self) -> int:
        """Number of UI-related changed files."""
        return len(self.get_ui_files())


class GitDiffCollector:
    """Collects git diff information for UI consistency analysis.

    Provides methods to collect staged changes, unstaged changes,
    PR diffs, and commit ranges for change-aware analysis.
    """

    UI_EXTENSIONS = [
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".jsx",
        ".tsx",
        ".vue",
        ".svelte",
        ".html",
        ".htm",
    ]

    def __init__(
        self,
        project_path: Path | str,
        cache_ttl_seconds: int = 30,
    ):
        """Initialize the git diff collector.

        Args:
            project_path: Path to the git repository.
            cache_ttl_seconds: Cache time-to-live in seconds.
        """
        self.project_path = Path(project_path)
        self._cache: dict[str, tuple[DiffResult, float]] = {}
        self._cache_ttl = cache_ttl_seconds

    def collect_staged(self) -> DiffResult:
        """Collect staged changes (for pre-commit).

        Returns:
            DiffResult containing staged file changes.
        """
        return self._get_cached_or_compute(
            "staged",
            lambda: self._collect_diff("--cached", "HEAD", "staged"),
        )

    def collect_unstaged(self) -> DiffResult:
        """Collect unstaged working tree changes.

        Returns:
            DiffResult containing unstaged file changes.
        """
        return self._get_cached_or_compute(
            "unstaged",
            lambda: self._collect_diff("", "", "unstaged"),
        )

    def collect_all_uncommitted(self) -> DiffResult:
        """Collect both staged and unstaged changes.

        Returns:
            Combined DiffResult with all uncommitted changes.
        """
        staged = self.collect_staged()
        unstaged = self.collect_unstaged()

        # Merge changes, preferring staged state for files in both
        seen_paths = set()
        combined_changes = []

        for change in staged.changes:
            seen_paths.add(change.file_path)
            combined_changes.append(change)

        for change in unstaged.changes:
            if change.file_path not in seen_paths:
                combined_changes.append(change)

        return DiffResult(
            changes=combined_changes,
            base_ref="HEAD",
            target_ref="working tree",
        )

    def collect_pr_diff(self, base_branch: str = "main") -> DiffResult:
        """Collect changes in current branch vs base branch (for CI).

        Args:
            base_branch: The base branch to diff against.

        Returns:
            DiffResult containing PR changes.
        """
        cache_key = f"pr:{base_branch}"
        return self._get_cached_or_compute(
            cache_key,
            lambda: self._collect_diff(f"{base_branch}...", "HEAD", base_branch),
        )

    def collect_commit_range(self, from_ref: str, to_ref: str = "HEAD") -> DiffResult:
        """Collect changes between two commits.

        Args:
            from_ref: Starting commit reference.
            to_ref: Ending commit reference (default HEAD).

        Returns:
            DiffResult containing changes in the range.
        """
        cache_key = f"range:{from_ref}:{to_ref}"
        return self._get_cached_or_compute(
            cache_key,
            lambda: self._collect_diff(f"{from_ref}..{to_ref}", to_ref, from_ref),
        )

    def _collect_diff(
        self, diff_args: str, target_ref: str, base_ref: str
    ) -> DiffResult:
        """Collect diff with given arguments.

        Args:
            diff_args: Arguments to pass to git diff.
            target_ref: The target reference being compared.
            base_ref: The base reference.

        Returns:
            DiffResult with parsed file changes.
        """
        # First get the list of changed files with their status
        status_output = self._run_git_command(
            ["diff", "--name-status"] + (diff_args.split() if diff_args else [])
        )

        changes = []
        for line in status_output.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status = parts[0][0]  # First character is the status
            file_path = Path(parts[-1])  # Last part is always the (new) file path
            old_path = Path(parts[1]) if len(parts) > 2 else None

            # Map git status to change type
            if status == "A":
                change_type = "added"
            elif status == "M":
                change_type = "modified"
            elif status == "D":
                change_type = "deleted"
            elif status.startswith("R"):
                change_type = "renamed"
            else:
                change_type = "modified"  # Default for unknown

            # Get line-level changes for non-deleted files
            added_lines = []
            deleted_lines = []

            if change_type != "deleted":
                line_info = self._get_line_changes(file_path, diff_args)
                added_lines = line_info["added"]
                deleted_lines = line_info["deleted"]

            changes.append(
                FileChange(
                    file_path=file_path,
                    change_type=change_type,
                    added_lines=added_lines,
                    deleted_lines=deleted_lines,
                    old_path=old_path if change_type == "renamed" else None,
                )
            )

        return DiffResult(
            changes=changes,
            base_ref=base_ref,
            target_ref=target_ref,
        )

    def _get_line_changes(
        self, file_path: Path, diff_args: str
    ) -> dict[str, list[tuple[int, int]]]:
        """Get line-level changes for a specific file.

        Args:
            file_path: Path to the file.
            diff_args: Arguments for git diff.

        Returns:
            Dict with 'added' and 'deleted' line ranges.
        """
        result = {"added": [], "deleted": []}

        try:
            args = ["diff", "-U0"] + (diff_args.split() if diff_args else [])
            args.extend(["--", str(file_path)])
            diff_output = self._run_git_command(args)

            # Parse hunk headers to find line ranges
            for line in diff_output.split("\n"):
                if line.startswith("@@"):
                    # Parse @@ -old,count +new,count @@ format
                    old_range, new_range = self._parse_hunk_header(line)
                    if old_range[1] > 0:  # Lines were deleted
                        result["deleted"].append(old_range)
                    if new_range[1] > 0:  # Lines were added
                        end = new_range[0] + new_range[1] - 1
                        result["added"].append((new_range[0], end))

        except Exception:
            # If we can't get line info, assume entire file changed
            pass

        return result

    def _parse_hunk_header(
        self, header: str
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Parse @@ -a,b +c,d @@ format.

        Args:
            header: The hunk header line.

        Returns:
            Tuple of ((old_start, old_count), (new_start, new_count)).
        """
        import re

        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", header)
        if not match:
            return ((0, 0), (0, 0))

        old_start = int(match.group(1))
        old_count = int(match.group(2)) if match.group(2) else 1
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) else 1

        return ((old_start, old_count), (new_start, new_count))

    def _run_git_command(self, args: list[str]) -> str:
        """Run git command and return stdout.

        Args:
            args: List of git command arguments.

        Returns:
            Command stdout as string.

        Raises:
            subprocess.CalledProcessError: If git command fails.
        """
        result = subprocess.run(
            ["git"] + args,
            cwd=self.project_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def _get_cached_or_compute(
        self,
        cache_key: str,
        compute_fn,
    ) -> DiffResult:
        """Get from cache or compute and cache result.

        Args:
            cache_key: Key for the cache.
            compute_fn: Function to compute the result if not cached.

        Returns:
            Cached or newly computed DiffResult.
        """
        now = time.time()

        if cache_key in self._cache:
            result, timestamp = self._cache[cache_key]
            if now - timestamp < self._cache_ttl:
                return result

        result = compute_fn()
        self._cache[cache_key] = (result, now)
        return result

    def is_line_new(self, file_path: Path, line_number: int) -> bool:
        """Check if a specific line is part of new/modified content.

        Convenience method for quick line status checks.

        Args:
            file_path: Path to the file.
            line_number: Line number to check.

        Returns:
            True if the line is in a newly added or modified range.
        """
        diff = self.collect_all_uncommitted()

        for change in diff.changes:
            if change.file_path == file_path or str(change.file_path) == str(file_path):
                return change.contains_line(line_number)

        return False

    def clear_cache(self) -> None:
        """Clear the diff cache."""
        self._cache.clear()
