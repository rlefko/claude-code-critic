"""Integration tests for git-aware incremental indexing.

These tests verify the incremental indexing workflow with actual git operations.
They require a git repository and can be run with:
    pytest tests/integration/test_incremental_indexing.py -v
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_indexer.git import ChangeSet, GitChangeDetector


class TestGitChangeDetectorIntegration:
    """Integration tests for GitChangeDetector with real git repos."""

    @pytest.fixture
    def git_repo(self, tmp_path: Path):
        """Create a temporary git repository."""
        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        # Configure git user for commits
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        # Create initial file and commit
        (tmp_path / "initial.py").write_text("# Initial file\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        return tmp_path

    def test_detect_changes_in_git_repo(self, git_repo: Path):
        """Test that changes are detected in a real git repo."""
        detector = GitChangeDetector(git_repo)

        assert detector.is_git_repo() is True
        assert detector.get_current_commit() is not None

    def test_detect_staged_changes(self, git_repo: Path):
        """Test detecting staged changes."""
        # Create and stage a new file
        new_file = git_repo / "new_file.py"
        new_file.write_text("# New file\n")
        subprocess.run(["git", "add", str(new_file)], cwd=git_repo, check=True)

        detector = GitChangeDetector(git_repo)
        changes = detector.get_staged_files()

        assert changes.has_changes
        assert any(f.name == "new_file.py" for f in changes.added_files)

    def test_detect_modified_files(self, git_repo: Path):
        """Test detecting modified files."""
        # Modify the initial file
        initial_file = git_repo / "initial.py"
        initial_file.write_text("# Modified content\n")
        subprocess.run(["git", "add", str(initial_file)], cwd=git_repo, check=True)

        detector = GitChangeDetector(git_repo)
        changes = detector.get_staged_files()

        assert changes.has_changes
        assert any(f.name == "initial.py" for f in changes.modified_files)

    def test_detect_deleted_files(self, git_repo: Path):
        """Test detecting deleted files."""
        # Delete the initial file
        initial_file = git_repo / "initial.py"
        initial_file.unlink()
        subprocess.run(["git", "add", str(initial_file)], cwd=git_repo, check=True)

        detector = GitChangeDetector(git_repo)
        changes = detector.get_staged_files()

        assert changes.has_changes
        assert "initial.py" in changes.deleted_files

    def test_detect_renamed_files(self, git_repo: Path):
        """Test detecting renamed files."""
        # Rename the file using git mv
        subprocess.run(
            ["git", "mv", "initial.py", "renamed.py"],
            cwd=git_repo,
            check=True,
        )

        detector = GitChangeDetector(git_repo)
        changes = detector.get_staged_files()

        assert changes.has_changes
        # Either detected as rename or as delete+add
        has_rename = any(
            old == "initial.py" and new == "renamed.py"
            for old, new in changes.renamed_files
        )
        has_delete_add = "initial.py" in changes.deleted_files and any(
            f.name == "renamed.py" for f in changes.added_files
        )
        assert has_rename or has_delete_add

    def test_detect_changes_since_commit(self, git_repo: Path):
        """Test detecting changes since a specific commit."""
        # Get the initial commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        initial_commit = result.stdout.strip()

        # Make some changes and commit
        (git_repo / "new.py").write_text("# New file\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add new file"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        detector = GitChangeDetector(git_repo)
        changes = detector.detect_changes(since_commit=initial_commit)

        assert changes.has_changes
        assert any(f.name == "new.py" for f in changes.added_files)

    def test_non_git_directory(self, tmp_path: Path):
        """Test behavior in non-git directory."""
        detector = GitChangeDetector(tmp_path)

        assert detector.is_git_repo() is False
        assert detector.get_current_commit() is None

        # Staged files should return empty set
        changes = detector.get_staged_files()
        assert not changes.has_changes
        assert changes.is_git_repo is False


class TestIncrementalIndexingWorkflow:
    """Test the full incremental indexing workflow."""

    @pytest.fixture
    def mock_indexer(self):
        """Create a mock CoreIndexer."""
        indexer = MagicMock()
        indexer.project_path = Path("/test/project")
        indexer._load_state.return_value = {}
        indexer.index_files.return_value = MagicMock(
            success=True,
            files_processed=1,
            entities_created=5,
            relations_created=3,
            implementation_chunks_created=2,
            errors=None,
            warnings=None,
        )
        indexer.vector_store.update_file_paths.return_value = MagicMock(
            success=True, items_processed=1
        )
        return indexer

    def test_changeset_workflow(self):
        """Test creating and using a ChangeSet."""
        change_set = ChangeSet(
            added_files=[Path("/project/new.py")],
            modified_files=[Path("/project/modified.py")],
            deleted_files=["deleted.py"],
            renamed_files=[("old_name.py", "new_name.py")],
            base_commit="abc123",
            is_git_repo=True,
        )

        # Verify properties
        assert change_set.has_changes
        assert len(change_set.files_to_index) == 2
        assert (
            change_set.total_files == 4
        )  # 1 added + 1 modified + 1 deleted + 1 renamed
        assert "via git" in change_set.summary()

    def test_hash_fallback_detection(self, tmp_path: Path):
        """Test hash-based detection as fallback."""
        # Create some files
        (tmp_path / "file1.py").write_text("content 1")
        (tmp_path / "file2.py").write_text("content 2")

        detector = GitChangeDetector(tmp_path)
        previous_state = {}  # Empty state means all files are new

        changes = detector._detect_via_hash(previous_state)

        assert changes.has_changes
        assert changes.is_git_repo is False
        assert len(changes.added_files) >= 2
