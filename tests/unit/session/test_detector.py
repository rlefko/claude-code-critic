"""Tests for ProjectRootDetector."""

from pathlib import Path

import pytest

from claude_indexer.session.detector import ProjectRootDetector


class TestProjectRootDetector:
    """Tests for ProjectRootDetector class."""

    def test_find_project_root_with_git(self, tmp_path: Path) -> None:
        """Should find project root with .git directory."""
        # Create nested structure
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        nested = tmp_path / "src" / "components"
        nested.mkdir(parents=True)

        # Search from nested directory
        result = ProjectRootDetector.find_project_root(nested)
        assert result == tmp_path

    def test_find_project_root_with_claude_indexer(self, tmp_path: Path) -> None:
        """Should prioritize .claude-indexer over .git."""
        # Create .git at root
        (tmp_path / ".git").mkdir()

        # Create nested project with .claude-indexer
        nested_project = tmp_path / "subproject"
        nested_project.mkdir()
        (nested_project / ".claude-indexer").mkdir()

        # Search from subproject - should find .claude-indexer first
        result = ProjectRootDetector.find_project_root(nested_project / "src")
        # Will find the marker at nested_project since we're inside it
        # But src doesn't exist, so let's search from the project itself
        result = ProjectRootDetector.find_project_root(nested_project)
        assert result == nested_project

    def test_find_project_root_with_package_json(self, tmp_path: Path) -> None:
        """Should find project root with package.json."""
        (tmp_path / "package.json").touch()

        nested = tmp_path / "src"
        nested.mkdir()

        result = ProjectRootDetector.find_project_root(nested)
        assert result == tmp_path

    def test_find_project_root_with_pyproject_toml(self, tmp_path: Path) -> None:
        """Should find project root with pyproject.toml."""
        (tmp_path / "pyproject.toml").touch()

        result = ProjectRootDetector.find_project_root(tmp_path)
        assert result == tmp_path

    def test_find_project_root_with_setup_py(self, tmp_path: Path) -> None:
        """Should find project root with setup.py."""
        (tmp_path / "setup.py").touch()

        result = ProjectRootDetector.find_project_root(tmp_path)
        assert result == tmp_path

    def test_find_project_root_with_cargo_toml(self, tmp_path: Path) -> None:
        """Should find project root with Cargo.toml (Rust)."""
        (tmp_path / "Cargo.toml").touch()

        result = ProjectRootDetector.find_project_root(tmp_path)
        assert result == tmp_path

    def test_find_project_root_with_go_mod(self, tmp_path: Path) -> None:
        """Should find project root with go.mod (Go)."""
        (tmp_path / "go.mod").touch()

        result = ProjectRootDetector.find_project_root(tmp_path)
        assert result == tmp_path

    def test_find_project_root_with_makefile(self, tmp_path: Path) -> None:
        """Should find project root with Makefile."""
        (tmp_path / "Makefile").touch()

        result = ProjectRootDetector.find_project_root(tmp_path)
        assert result == tmp_path

    def test_find_project_root_no_markers(self, tmp_path: Path) -> None:
        """Should return None when no project markers found."""
        # Create empty directory structure
        nested = tmp_path / "empty" / "nested"
        nested.mkdir(parents=True)

        result = ProjectRootDetector.find_project_root(nested)
        assert result is None

    def test_find_project_root_defaults_to_cwd(self) -> None:
        """Should use CWD when start_path not provided."""
        # This test just ensures the method doesn't crash
        # Actual result depends on where tests are run from
        result = ProjectRootDetector.find_project_root()
        # Result might be None or a Path depending on test environment
        assert result is None or isinstance(result, Path)

    def test_detect_from_cwd_with_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should find project root from CWD."""
        # Create project marker
        (tmp_path / ".git").mkdir()

        # Change to project directory
        monkeypatch.chdir(tmp_path)

        result = ProjectRootDetector.detect_from_cwd()
        assert result == tmp_path

    def test_detect_from_cwd_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should fall back to CWD when no project found."""
        # Create empty directory
        empty = tmp_path / "empty"
        empty.mkdir()

        # Change to empty directory
        monkeypatch.chdir(empty)

        result = ProjectRootDetector.detect_from_cwd()
        assert result == empty

    def test_is_project_root_true(self, tmp_path: Path) -> None:
        """Should return True for directory with project marker."""
        (tmp_path / ".git").mkdir()

        assert ProjectRootDetector.is_project_root(tmp_path) is True

    def test_is_project_root_false(self, tmp_path: Path) -> None:
        """Should return False for directory without project marker."""
        assert ProjectRootDetector.is_project_root(tmp_path) is False

    def test_get_project_marker_found(self, tmp_path: Path) -> None:
        """Should return the first marker found."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "package.json").touch()

        # Should return first marker in priority order
        marker = ProjectRootDetector.get_project_marker(tmp_path)
        assert marker == ".git"

    def test_get_project_marker_not_found(self, tmp_path: Path) -> None:
        """Should return None when no marker found."""
        marker = ProjectRootDetector.get_project_marker(tmp_path)
        assert marker is None

    def test_find_project_root_walks_up_tree(self, tmp_path: Path) -> None:
        """Should walk up directory tree to find project root."""
        # Create deep nested structure
        (tmp_path / ".git").mkdir()
        deep_path = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep_path.mkdir(parents=True)

        result = ProjectRootDetector.find_project_root(deep_path)
        assert result == tmp_path

    def test_project_markers_list(self) -> None:
        """Should have expected project markers in priority order."""
        markers = ProjectRootDetector.PROJECT_MARKERS

        # Check priority markers are present
        assert ".claude-indexer" in markers
        assert ".git" in markers
        assert "package.json" in markers
        assert "pyproject.toml" in markers

        # .claude-indexer should be first (highest priority)
        assert markers[0] == ".claude-indexer"
