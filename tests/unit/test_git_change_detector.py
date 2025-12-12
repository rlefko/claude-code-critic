"""Unit tests for git change detector."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_indexer.git import ChangeSet, GitChangeDetector


class TestChangeSet:
    """Tests for ChangeSet dataclass."""

    def test_create_empty_changeset(self):
        """Test creating empty ChangeSet."""
        change_set = ChangeSet()

        assert change_set.added_files == []
        assert change_set.modified_files == []
        assert change_set.deleted_files == []
        assert change_set.renamed_files == []
        assert change_set.base_commit is None
        assert change_set.is_git_repo is True

    def test_create_changeset_with_changes(self):
        """Test creating ChangeSet with changes."""
        change_set = ChangeSet(
            added_files=[Path("/project/new.py")],
            modified_files=[Path("/project/modified.py")],
            deleted_files=["old.py"],
            renamed_files=[("old_name.py", "new_name.py")],
            base_commit="abc123",
            is_git_repo=True,
        )

        assert len(change_set.added_files) == 1
        assert len(change_set.modified_files) == 1
        assert len(change_set.deleted_files) == 1
        assert len(change_set.renamed_files) == 1
        assert change_set.base_commit == "abc123"

    def test_has_changes_true(self):
        """Test has_changes returns True when there are changes."""
        # Added files
        assert ChangeSet(added_files=[Path("/a.py")]).has_changes
        # Modified files
        assert ChangeSet(modified_files=[Path("/a.py")]).has_changes
        # Deleted files
        assert ChangeSet(deleted_files=["a.py"]).has_changes
        # Renamed files
        assert ChangeSet(renamed_files=[("old.py", "new.py")]).has_changes

    def test_has_changes_false(self):
        """Test has_changes returns False when no changes."""
        assert not ChangeSet().has_changes

    def test_total_files(self):
        """Test total_files count."""
        change_set = ChangeSet(
            added_files=[Path("/a.py"), Path("/b.py")],
            modified_files=[Path("/c.py")],
            deleted_files=["d.py"],
            renamed_files=[("old.py", "new.py")],
        )

        assert change_set.total_files == 5

    def test_files_to_index(self):
        """Test files_to_index combines added and modified."""
        change_set = ChangeSet(
            added_files=[Path("/added.py")],
            modified_files=[Path("/modified.py")],
            deleted_files=["deleted.py"],  # Should not be included
        )

        files = change_set.files_to_index
        assert len(files) == 2
        assert Path("/added.py") in files
        assert Path("/modified.py") in files

    def test_summary_no_changes(self):
        """Test summary with no changes."""
        assert ChangeSet().summary() == "No changes detected"

    def test_summary_with_changes(self):
        """Test summary with various changes."""
        change_set = ChangeSet(
            added_files=[Path("/a.py")],
            modified_files=[Path("/b.py"), Path("/c.py")],
            deleted_files=["d.py"],
            renamed_files=[("e.py", "f.py")],
            is_git_repo=True,
        )

        summary = change_set.summary()
        assert "1 added" in summary
        assert "2 modified" in summary
        assert "1 deleted" in summary
        assert "1 renamed" in summary
        assert "via git" in summary

    def test_summary_non_git(self):
        """Test summary for non-git detection."""
        change_set = ChangeSet(
            added_files=[Path("/a.py")],
            is_git_repo=False,
        )

        assert "via hash comparison" in change_set.summary()


class TestGitChangeDetector:
    """Tests for GitChangeDetector."""

    @pytest.fixture
    def detector(self, tmp_path: Path) -> GitChangeDetector:
        """Create a detector with a temp path."""
        return GitChangeDetector(tmp_path)

    def test_init(self, tmp_path: Path):
        """Test GitChangeDetector initialization."""
        detector = GitChangeDetector(tmp_path)

        assert detector.project_path == tmp_path.resolve()
        assert detector.file_hash_cache is None
        assert detector._is_git_repo is None

    def test_init_with_cache(self, tmp_path: Path):
        """Test initialization with file hash cache."""
        mock_cache = MagicMock()
        detector = GitChangeDetector(tmp_path, file_hash_cache=mock_cache)

        assert detector.file_hash_cache is mock_cache

    @patch("subprocess.run")
    def test_is_git_repo_true(self, mock_run: MagicMock, tmp_path: Path):
        """Test is_git_repo returns True for git repos."""
        mock_run.return_value = MagicMock(returncode=0)
        detector = GitChangeDetector(tmp_path)

        assert detector.is_git_repo() is True
        assert detector._is_git_repo is True  # Cached

    @patch("subprocess.run")
    def test_is_git_repo_false(self, mock_run: MagicMock, tmp_path: Path):
        """Test is_git_repo returns False for non-git dirs."""
        mock_run.return_value = MagicMock(returncode=128)
        detector = GitChangeDetector(tmp_path)

        assert detector.is_git_repo() is False
        assert detector._is_git_repo is False  # Cached

    @patch("subprocess.run")
    def test_is_git_repo_caches_result(self, mock_run: MagicMock, tmp_path: Path):
        """Test that is_git_repo caches the result."""
        mock_run.return_value = MagicMock(returncode=0)
        detector = GitChangeDetector(tmp_path)

        detector.is_git_repo()
        detector.is_git_repo()
        detector.is_git_repo()

        # Should only call subprocess once
        assert mock_run.call_count == 1

    @patch("subprocess.run")
    def test_get_current_commit(self, mock_run: MagicMock, tmp_path: Path):
        """Test getting current commit."""
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
        detector = GitChangeDetector(tmp_path)
        detector._is_git_repo = True

        commit = detector.get_current_commit()

        assert commit == "abc123"

    @patch("subprocess.run")
    def test_get_current_commit_non_git(self, mock_run: MagicMock, tmp_path: Path):
        """Test get_current_commit returns None for non-git."""
        mock_run.return_value = MagicMock(returncode=128)
        detector = GitChangeDetector(tmp_path)
        detector._is_git_repo = False

        assert detector.get_current_commit() is None

    def test_parse_git_status_added(self, detector: GitChangeDetector):
        """Test parsing added files from git output."""
        output = "A\tsrc/new_file.py"
        (detector.project_path / "src").mkdir()
        (detector.project_path / "src/new_file.py").touch()

        result = detector._parse_git_status(output)

        assert len(result.added_files) == 1
        assert result.added_files[0].name == "new_file.py"
        assert len(result.modified_files) == 0
        assert len(result.deleted_files) == 0

    def test_parse_git_status_modified(self, detector: GitChangeDetector):
        """Test parsing modified files from git output."""
        output = "M\tsrc/modified.py"
        (detector.project_path / "src").mkdir()
        (detector.project_path / "src/modified.py").touch()

        result = detector._parse_git_status(output)

        assert len(result.added_files) == 0
        assert len(result.modified_files) == 1
        assert result.modified_files[0].name == "modified.py"

    def test_parse_git_status_deleted(self, detector: GitChangeDetector):
        """Test parsing deleted files from git output."""
        output = "D\tsrc/deleted.py"

        result = detector._parse_git_status(output)

        assert len(result.deleted_files) == 1
        assert result.deleted_files[0] == "src/deleted.py"

    def test_parse_git_status_renamed(self, detector: GitChangeDetector):
        """Test parsing renamed files from git output."""
        output = "R100\told_name.py\tnew_name.py"
        (detector.project_path / "new_name.py").touch()

        result = detector._parse_git_status(output)

        assert len(result.renamed_files) == 1
        assert result.renamed_files[0] == ("old_name.py", "new_name.py")
        # Renamed file should also be in modified for re-indexing
        assert len(result.modified_files) == 1

    def test_parse_git_status_renamed_partial_similarity(
        self, detector: GitChangeDetector
    ):
        """Test parsing renamed files with partial similarity."""
        output = "R085\tsrc/old.py\tsrc/new.py"
        (detector.project_path / "src").mkdir()
        (detector.project_path / "src/new.py").touch()

        result = detector._parse_git_status(output)

        assert len(result.renamed_files) == 1
        assert result.renamed_files[0] == ("src/old.py", "src/new.py")

    def test_parse_git_status_copied(self, detector: GitChangeDetector):
        """Test parsing copied files from git output."""
        output = "C100\tsrc/original.py\tsrc/copy.py"
        (detector.project_path / "src").mkdir()
        (detector.project_path / "src/copy.py").touch()

        result = detector._parse_git_status(output)

        # Copied files should be treated as added
        assert len(result.added_files) == 1

    def test_parse_git_status_multiple(self, detector: GitChangeDetector):
        """Test parsing multiple changes."""
        output = """A\tnew.py
M\tmodified.py
D\tdeleted.py
R100\told.py\trenamed.py"""
        (detector.project_path / "new.py").touch()
        (detector.project_path / "modified.py").touch()
        (detector.project_path / "renamed.py").touch()

        result = detector._parse_git_status(output)

        assert len(result.added_files) == 1
        assert len(result.modified_files) == 2  # modified + renamed
        assert len(result.deleted_files) == 1
        assert len(result.renamed_files) == 1

    def test_parse_git_status_empty(self, detector: GitChangeDetector):
        """Test parsing empty output."""
        result = detector._parse_git_status("")

        assert not result.has_changes

    def test_parse_git_status_skips_missing_files(self, detector: GitChangeDetector):
        """Test that files that don't exist are skipped."""
        output = "A\tnonexistent.py"

        result = detector._parse_git_status(output)

        assert len(result.added_files) == 0  # Skipped because file doesn't exist

    @patch.object(GitChangeDetector, "_run_git_command")
    @patch.object(GitChangeDetector, "is_git_repo")
    def test_get_staged_files(
        self, mock_is_git: MagicMock, mock_git: MagicMock, detector: GitChangeDetector
    ):
        """Test get_staged_files calls git with correct args."""
        mock_is_git.return_value = True
        mock_git.return_value = ""

        detector.get_staged_files()

        # Find the diff call (there may also be a rev-parse call)
        diff_calls = [call for call in mock_git.call_args_list if "diff" in call[0][0]]
        assert len(diff_calls) == 1
        call_args = diff_calls[0][0][0]
        assert "--cached" in call_args
        assert "--name-status" in call_args
        assert "-M" in call_args

    @patch.object(GitChangeDetector, "_run_git_command")
    @patch.object(GitChangeDetector, "is_git_repo")
    def test_get_staged_files_non_git(
        self, mock_is_git: MagicMock, mock_git: MagicMock, detector: GitChangeDetector
    ):
        """Test get_staged_files returns empty for non-git."""
        mock_is_git.return_value = False

        result = detector.get_staged_files()

        assert not result.has_changes
        assert result.is_git_repo is False
        mock_git.assert_not_called()

    @patch.object(GitChangeDetector, "_run_git_command")
    @patch.object(GitChangeDetector, "is_git_repo")
    @patch.object(GitChangeDetector, "get_merge_base")
    def test_get_branch_diff(
        self,
        mock_merge_base: MagicMock,
        mock_is_git: MagicMock,
        mock_git: MagicMock,
        detector: GitChangeDetector,
    ):
        """Test get_branch_diff uses merge base."""
        mock_is_git.return_value = True
        mock_merge_base.return_value = "abc123"
        mock_git.return_value = ""

        detector.get_branch_diff("main")

        mock_merge_base.assert_called_once_with("main")
        # Find the diff call
        diff_calls = [
            call
            for call in mock_git.call_args_list
            if len(call[0]) > 0 and "diff" in call[0][0]
        ]
        assert len(diff_calls) == 1
        call_args = " ".join(diff_calls[0][0][0])
        assert "abc123..HEAD" in call_args

    @patch.object(GitChangeDetector, "_run_git_command")
    @patch.object(GitChangeDetector, "is_git_repo")
    def test_get_commit_range(
        self, mock_is_git: MagicMock, mock_git: MagicMock, detector: GitChangeDetector
    ):
        """Test get_commit_range."""
        mock_is_git.return_value = True
        mock_git.return_value = ""

        detector.get_commit_range("HEAD~5", "HEAD")

        # Find the diff call
        diff_calls = [
            call
            for call in mock_git.call_args_list
            if len(call[0]) > 0 and "diff" in call[0][0]
        ]
        assert len(diff_calls) == 1
        call_args = " ".join(diff_calls[0][0][0])
        assert "HEAD~5..HEAD" in call_args

    @patch.object(GitChangeDetector, "_run_git_command")
    @patch.object(GitChangeDetector, "is_git_repo")
    def test_get_uncommitted_changes(
        self, mock_is_git: MagicMock, mock_git: MagicMock, detector: GitChangeDetector
    ):
        """Test get_uncommitted_changes."""
        mock_is_git.return_value = True
        mock_git.return_value = ""

        detector.get_uncommitted_changes()

        call_args = mock_git.call_args[0][0]
        assert "HEAD" in call_args

    @patch.object(GitChangeDetector, "is_git_repo")
    def test_detect_changes_with_commit(
        self, mock_is_git: MagicMock, detector: GitChangeDetector
    ):
        """Test detect_changes with since_commit."""
        mock_is_git.return_value = True

        with patch.object(detector, "_detect_via_git") as mock_detect:
            mock_detect.return_value = ChangeSet()
            detector.detect_changes(since_commit="HEAD~5")

            mock_detect.assert_called_once()
            call_args = mock_detect.call_args[0][0]
            assert "HEAD~5" in call_args

    @patch.object(GitChangeDetector, "is_git_repo")
    def test_detect_changes_non_git_fallback(
        self, mock_is_git: MagicMock, detector: GitChangeDetector
    ):
        """Test detect_changes falls back to hash for non-git."""
        mock_is_git.return_value = False

        with patch.object(detector, "_detect_via_hash") as mock_detect:
            mock_detect.return_value = ChangeSet(is_git_repo=False)
            result = detector.detect_changes(previous_state={})

            mock_detect.assert_called_once()
            assert result.is_git_repo is False

    def test_detect_via_hash_new_files(self, detector: GitChangeDetector):
        """Test hash-based detection finds new files."""
        # Create a file
        test_file = detector.project_path / "new.py"
        test_file.write_text("print('hello')")

        result = detector._detect_via_hash({})

        # Should detect the new file
        assert any(f.name == "new.py" for f in result.added_files)

    def test_detect_via_hash_deleted_files(self, detector: GitChangeDetector):
        """Test hash-based detection finds deleted files."""
        previous_state = {"deleted.py": {"hash": "abc123"}}

        result = detector._detect_via_hash(previous_state)

        assert "deleted.py" in result.deleted_files

    def test_detect_via_hash_modified_files(self, detector: GitChangeDetector):
        """Test hash-based detection finds modified files."""
        test_file = detector.project_path / "modified.py"
        test_file.write_text("new content")

        previous_state = {"modified.py": {"hash": "old_hash"}}

        result = detector._detect_via_hash(previous_state)

        assert any(f.name == "modified.py" for f in result.modified_files)

    def test_should_skip_common_patterns(self, detector: GitChangeDetector):
        """Test _should_skip filters common patterns."""
        assert detector._should_skip(Path("/project/.git/objects/abc"))
        assert detector._should_skip(Path("/project/.venv/lib/python/site.py"))
        assert detector._should_skip(Path("/project/node_modules/pkg/index.js"))
        assert detector._should_skip(Path("/project/__pycache__/module.pyc"))
        assert not detector._should_skip(Path("/project/src/main.py"))
