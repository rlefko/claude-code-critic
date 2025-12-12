"""Unit tests for git diff collector."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_indexer.ui.collectors.git_diff import (
    DiffResult,
    FileChange,
    GitDiffCollector,
)


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_create_file_change(self):
        """Test basic FileChange creation."""
        change = FileChange(
            file_path=Path("src/Button.tsx"),
            change_type="modified",
            added_lines=[(10, 20), (30, 35)],
            deleted_lines=[(5, 8)],
        )

        assert change.file_path == Path("src/Button.tsx")
        assert change.change_type == "modified"
        assert len(change.added_lines) == 2
        assert len(change.deleted_lines) == 1

    def test_contains_line_in_range(self):
        """Test contains_line for line within range."""
        change = FileChange(
            file_path=Path("test.tsx"),
            change_type="modified",
            added_lines=[(10, 20), (30, 40)],
        )

        assert change.contains_line(15)  # In first range
        assert change.contains_line(35)  # In second range
        assert change.contains_line(10)  # Start of range
        assert change.contains_line(20)  # End of range

    def test_contains_line_outside_range(self):
        """Test contains_line for line outside range."""
        change = FileChange(
            file_path=Path("test.tsx"),
            change_type="modified",
            added_lines=[(10, 20)],
        )

        assert not change.contains_line(5)
        assert not change.contains_line(25)
        assert not change.contains_line(9)
        assert not change.contains_line(21)

    def test_is_ui_file_default_extensions(self):
        """Test UI file detection with default extensions."""
        css_change = FileChange(Path("styles.css"), "modified")
        tsx_change = FileChange(Path("Button.tsx"), "modified")
        py_change = FileChange(Path("utils.py"), "modified")

        assert css_change.is_ui_file()
        assert tsx_change.is_ui_file()
        assert not py_change.is_ui_file()

    def test_is_ui_file_custom_extensions(self):
        """Test UI file detection with custom extensions."""
        change = FileChange(Path("custom.ext"), "modified")

        assert not change.is_ui_file()
        assert change.is_ui_file(extensions=[".ext"])

    def test_serialization_roundtrip(self):
        """Test to_dict and from_dict produce equivalent objects."""
        change = FileChange(
            file_path=Path("src/Component.tsx"),
            change_type="modified",
            added_lines=[(1, 10)],
            deleted_lines=[(5, 5)],
            old_path=None,
        )

        data = change.to_dict()
        restored = FileChange.from_dict(data)

        assert restored.file_path == change.file_path
        assert restored.change_type == change.change_type
        assert restored.added_lines == change.added_lines
        assert restored.deleted_lines == change.deleted_lines

    def test_rename_with_old_path(self):
        """Test FileChange with rename tracking."""
        change = FileChange(
            file_path=Path("src/NewName.tsx"),
            change_type="renamed",
            old_path=Path("src/OldName.tsx"),
        )

        data = change.to_dict()
        restored = FileChange.from_dict(data)

        assert restored.old_path == Path("src/OldName.tsx")


class TestDiffResult:
    """Tests for DiffResult dataclass."""

    def test_create_diff_result(self):
        """Test basic DiffResult creation."""
        changes = [
            FileChange(Path("a.tsx"), "added"),
            FileChange(Path("b.css"), "modified"),
        ]
        result = DiffResult(changes=changes, base_ref="main", target_ref="HEAD")

        assert len(result.changes) == 2
        assert result.base_ref == "main"
        assert result.target_ref == "HEAD"
        assert result.computed_at  # Auto-set timestamp

    def test_get_ui_files(self):
        """Test filtering for UI files."""
        changes = [
            FileChange(Path("Button.tsx"), "modified"),
            FileChange(Path("styles.css"), "added"),
            FileChange(Path("utils.py"), "modified"),
            FileChange(Path("Card.vue"), "modified"),
        ]
        result = DiffResult(changes=changes)

        ui_files = result.get_ui_files()

        assert len(ui_files) == 3
        paths = [str(f.file_path) for f in ui_files]
        assert "Button.tsx" in paths
        assert "styles.css" in paths
        assert "Card.vue" in paths
        assert "utils.py" not in paths

    def test_get_added_files(self):
        """Test filtering for added files."""
        changes = [
            FileChange(Path("new.tsx"), "added"),
            FileChange(Path("old.tsx"), "modified"),
        ]
        result = DiffResult(changes=changes)

        added = result.get_added_files()

        assert len(added) == 1
        assert added[0].file_path == Path("new.tsx")

    def test_get_modified_files(self):
        """Test filtering for modified files."""
        changes = [
            FileChange(Path("new.tsx"), "added"),
            FileChange(Path("old.tsx"), "modified"),
        ]
        result = DiffResult(changes=changes)

        modified = result.get_modified_files()

        assert len(modified) == 1
        assert modified[0].file_path == Path("old.tsx")

    def test_get_deleted_files(self):
        """Test filtering for deleted files."""
        changes = [
            FileChange(Path("removed.tsx"), "deleted"),
            FileChange(Path("kept.tsx"), "modified"),
        ]
        result = DiffResult(changes=changes)

        deleted = result.get_deleted_files()

        assert len(deleted) == 1
        assert deleted[0].file_path == Path("removed.tsx")

    def test_file_count_properties(self):
        """Test file count properties."""
        changes = [
            FileChange(Path("a.tsx"), "added"),
            FileChange(Path("b.css"), "modified"),
            FileChange(Path("c.py"), "modified"),
        ]
        result = DiffResult(changes=changes)

        assert result.file_count == 3
        assert result.ui_file_count == 2  # tsx and css

    def test_serialization_roundtrip(self):
        """Test to_dict and from_dict produce equivalent objects."""
        changes = [FileChange(Path("test.tsx"), "modified")]
        result = DiffResult(
            changes=changes,
            base_ref="main",
            target_ref="feature-branch",
        )

        data = result.to_dict()
        restored = DiffResult.from_dict(data)

        assert len(restored.changes) == 1
        assert restored.base_ref == result.base_ref
        assert restored.target_ref == result.target_ref


class TestGitDiffCollector:
    """Tests for GitDiffCollector."""

    @pytest.fixture
    def collector(self, tmp_path: Path) -> GitDiffCollector:
        """Create a collector with a temp path."""
        return GitDiffCollector(tmp_path)

    def test_ui_extensions(self):
        """Test UI extension list."""
        extensions = GitDiffCollector.UI_EXTENSIONS

        assert ".css" in extensions
        assert ".scss" in extensions
        assert ".tsx" in extensions
        assert ".jsx" in extensions
        assert ".vue" in extensions
        assert ".svelte" in extensions

    def test_parse_hunk_header_add(self, collector: GitDiffCollector):
        """Test parsing hunk header for additions."""
        header = "@@ -0,0 +1,10 @@"
        old_range, new_range = collector._parse_hunk_header(header)

        assert old_range == (0, 0)
        assert new_range == (1, 10)

    def test_parse_hunk_header_modify(self, collector: GitDiffCollector):
        """Test parsing hunk header for modifications."""
        header = "@@ -5,3 +5,5 @@"
        old_range, new_range = collector._parse_hunk_header(header)

        assert old_range == (5, 3)
        assert new_range == (5, 5)

    def test_parse_hunk_header_single_line(self, collector: GitDiffCollector):
        """Test parsing hunk header for single line changes."""
        header = "@@ -10 +10 @@"
        old_range, new_range = collector._parse_hunk_header(header)

        assert old_range == (10, 1)  # Default count is 1
        assert new_range == (10, 1)

    def test_parse_hunk_header_delete(self, collector: GitDiffCollector):
        """Test parsing hunk header for deletions."""
        header = "@@ -1,5 +0,0 @@"
        old_range, new_range = collector._parse_hunk_header(header)

        assert old_range == (1, 5)
        assert new_range == (0, 0)

    def test_parse_hunk_header_invalid(self, collector: GitDiffCollector):
        """Test parsing invalid hunk header."""
        header = "not a valid header"
        old_range, new_range = collector._parse_hunk_header(header)

        assert old_range == (0, 0)
        assert new_range == (0, 0)

    def test_cache_hit(self, collector: GitDiffCollector):
        """Test that cached results are returned."""
        result1 = DiffResult(changes=[], base_ref="test")

        # Prime the cache
        collector._cache["test_key"] = (result1, float("inf"))

        # Should return cached result
        cached = collector._get_cached_or_compute(
            "test_key",
            lambda: DiffResult(changes=[FileChange(Path("new.tsx"), "added")]),
        )

        assert cached is result1
        assert len(cached.changes) == 0  # Original cached result

    def test_cache_miss_computes(self, collector: GitDiffCollector):
        """Test that cache miss triggers computation."""
        computed = collector._get_cached_or_compute(
            "new_key",
            lambda: DiffResult(changes=[FileChange(Path("computed.tsx"), "added")]),
        )

        assert len(computed.changes) == 1
        assert computed.changes[0].file_path == Path("computed.tsx")

    def test_clear_cache(self, collector: GitDiffCollector):
        """Test cache clearing."""
        collector._cache["key1"] = (DiffResult(), 0)
        collector._cache["key2"] = (DiffResult(), 0)

        collector.clear_cache()

        assert len(collector._cache) == 0

    @patch.object(GitDiffCollector, "_run_git_command")
    def test_collect_staged_calls_git(
        self, mock_git: MagicMock, collector: GitDiffCollector
    ):
        """Test that collect_staged calls git with correct args."""
        mock_git.return_value = ""

        collector.collect_staged()

        # Should call git diff --name-status --cached
        calls = mock_git.call_args_list
        assert any("--cached" in str(call) for call in calls)

    @patch.object(GitDiffCollector, "_run_git_command")
    def test_collect_pr_diff_calls_git(
        self, mock_git: MagicMock, collector: GitDiffCollector
    ):
        """Test that collect_pr_diff calls git with branch comparison."""
        mock_git.return_value = ""

        collector.collect_pr_diff("develop")

        # Should compare against develop branch
        calls = mock_git.call_args_list
        assert any("develop" in str(call) for call in calls)

    @patch.object(GitDiffCollector, "collect_all_uncommitted")
    def test_is_line_new(self, mock_collect: MagicMock, collector: GitDiffCollector):
        """Test is_line_new helper method."""
        mock_collect.return_value = DiffResult(
            changes=[
                FileChange(
                    file_path=Path("test.tsx"),
                    change_type="modified",
                    added_lines=[(10, 20)],
                )
            ]
        )

        assert collector.is_line_new(Path("test.tsx"), 15)
        assert not collector.is_line_new(Path("test.tsx"), 5)
        assert not collector.is_line_new(Path("other.tsx"), 15)
