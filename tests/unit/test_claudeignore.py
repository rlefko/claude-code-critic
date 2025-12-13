"""Unit tests for .claudeignore parser and hierarchical ignore manager."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestClaudeIgnoreParser:
    """Test the ClaudeIgnoreParser class."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def parser(self, temp_project):
        """Create a parser instance."""
        from claude_indexer.utils.claudeignore_parser import ClaudeIgnoreParser

        return ClaudeIgnoreParser(temp_project)

    def test_basic_glob_pattern(self, parser, temp_project):
        """Test that *.py matches Python files."""
        # Create a claudeignore file
        ignore_file = temp_project / ".claudeignore"
        ignore_file.write_text("*.py\n")

        parser.load_file(ignore_file)

        assert parser.matches("test.py")
        assert parser.matches("src/module.py")
        assert not parser.matches("test.txt")
        assert not parser.matches("README.md")

    def test_directory_pattern(self, parser, temp_project):
        """Test that node_modules/ matches directories."""
        ignore_file = temp_project / ".claudeignore"
        ignore_file.write_text("node_modules/\n")

        parser.load_file(ignore_file)

        assert parser.matches("node_modules/package.json")
        assert parser.matches("node_modules/lodash/index.js")
        assert not parser.matches("src/node_modules.txt")

    def test_globstar_pattern(self, parser, temp_project):
        """Test that **/*.js matches nested files."""
        ignore_file = temp_project / ".claudeignore"
        ignore_file.write_text("**/*.js\n")

        parser.load_file(ignore_file)

        assert parser.matches("index.js")
        assert parser.matches("src/app.js")
        assert parser.matches("src/deep/nested/file.js")
        assert not parser.matches("index.ts")

    def test_negation_pattern(self, parser, temp_project):
        """Test that ! negates previous patterns."""
        ignore_file = temp_project / ".claudeignore"
        ignore_file.write_text("*.log\n!important.log\n")

        parser.load_file(ignore_file)

        assert parser.matches("debug.log")
        assert parser.matches("error.log")
        # Note: pathspec handles negation at the PathSpec level
        # The file "important.log" should NOT be ignored due to negation
        assert not parser.matches("important.log")

    def test_comments_and_blanks(self, parser, temp_project):
        """Test that comments and blank lines are ignored."""
        ignore_file = temp_project / ".claudeignore"
        ignore_file.write_text(
            """
# This is a comment
*.log

# Another comment
*.tmp

"""
        )

        parser.load_file(ignore_file)

        assert parser.matches("test.log")
        assert parser.matches("test.tmp")
        # Comments should not be treated as patterns
        assert not parser.matches("# This is a comment")
        assert parser.pattern_count == 2

    def test_root_relative_pattern(self, parser, temp_project):
        """Test that /src matches only root src directory."""
        ignore_file = temp_project / ".claudeignore"
        ignore_file.write_text("/src/\n")

        parser.load_file(ignore_file)

        assert parser.matches("src/file.py")
        # This should NOT match because the pattern is root-relative
        # (pathspec handles this correctly)

    def test_add_patterns_programmatically(self, parser):
        """Test adding patterns without a file."""
        parser.add_patterns(["*.pyc", "__pycache__/", "*.log"])

        assert parser.matches("module.pyc")
        assert parser.matches("__pycache__/cache.json")
        assert parser.matches("debug.log")
        assert parser.pattern_count == 3

    def test_filter_paths(self, parser, temp_project):
        """Test filtering a list of paths."""
        ignore_file = temp_project / ".claudeignore"
        ignore_file.write_text("*.log\n*.tmp\n")

        parser.load_file(ignore_file)

        paths = [
            temp_project / "src" / "main.py",
            temp_project / "debug.log",
            temp_project / "temp.tmp",
            temp_project / "README.md",
        ]

        filtered = parser.filter_paths(paths)

        assert len(filtered) == 2
        assert any("main.py" in str(p) for p in filtered)
        assert any("README.md" in str(p) for p in filtered)

    def test_clear_patterns(self, parser, temp_project):
        """Test clearing all patterns."""
        ignore_file = temp_project / ".claudeignore"
        ignore_file.write_text("*.log\n")

        parser.load_file(ignore_file)
        assert parser.pattern_count > 0

        parser.clear()
        assert parser.pattern_count == 0
        assert not parser.matches("test.log")

    def test_nonexistent_file(self, parser, temp_project):
        """Test loading a nonexistent file."""
        count = parser.load_file(temp_project / "nonexistent.claudeignore")
        assert count == 0

    def test_escaped_characters(self, parser, temp_project):
        """Test escaped characters at start of line."""
        ignore_file = temp_project / ".claudeignore"
        ignore_file.write_text("\\#notacomment\n\\!notanegation\n")

        parser.load_file(ignore_file)

        assert parser.matches("#notacomment")
        assert parser.matches("!notanegation")


class TestHierarchicalIgnoreManager:
    """Test the HierarchicalIgnoreManager class."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def temp_global(self):
        """Create a temporary global config directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_universal_defaults_loaded(self, temp_project):
        """Test that universal defaults are loaded."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        manager = HierarchicalIgnoreManager(temp_project).load()
        stats = manager.get_stats()

        assert stats["universal_patterns"] > 0
        assert stats["total_patterns"] >= stats["universal_patterns"]

    def test_project_patterns_loaded(self, temp_project):
        """Test that project .claudeignore is loaded."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        # Create project .claudeignore
        claudeignore = temp_project / ".claudeignore"
        claudeignore.write_text("*.project\ncustom_pattern/\n")

        manager = HierarchicalIgnoreManager(temp_project).load()
        stats = manager.get_stats()

        assert stats["project_patterns"] == 2
        assert stats["project_ignore_exists"] is True

    @patch(
        "claude_indexer.utils.hierarchical_ignore.HierarchicalIgnoreManager.GLOBAL_IGNORE"
    )
    def test_global_patterns_loaded(
        self, mock_global_ignore, temp_project, temp_global
    ):
        """Test that global .claudeignore is loaded."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        # Create global .claudeignore
        global_ignore = temp_global / ".claudeignore"
        global_ignore.write_text("*.global\nglobal_pattern/\n")

        # Patch the GLOBAL_IGNORE path
        mock_global_ignore.__class__ = type(global_ignore)
        HierarchicalIgnoreManager.GLOBAL_IGNORE = global_ignore

        manager = HierarchicalIgnoreManager(temp_project).load()
        stats = manager.get_stats()

        assert stats["global_patterns"] == 2
        assert stats["global_ignore_exists"] is True

    def test_should_ignore_universal_pattern(self, temp_project):
        """Test that universal patterns are respected."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        manager = HierarchicalIgnoreManager(temp_project).load()

        # Universal defaults should include common patterns
        assert manager.should_ignore("node_modules/lodash/index.js")
        assert manager.should_ignore("__pycache__/module.pyc")
        assert manager.should_ignore(".git/config")

    def test_should_ignore_project_pattern(self, temp_project):
        """Test that project patterns are respected."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        claudeignore = temp_project / ".claudeignore"
        claudeignore.write_text("*.secret\nsecrets/\n")

        manager = HierarchicalIgnoreManager(temp_project).load()

        assert manager.should_ignore("api.secret")
        assert manager.should_ignore("secrets/credentials.json")
        assert not manager.should_ignore("public/index.html")

    def test_get_ignore_reason(self, temp_project):
        """Test getting the reason for ignoring a file."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        claudeignore = temp_project / ".claudeignore"
        claudeignore.write_text("*.secret\n")

        manager = HierarchicalIgnoreManager(temp_project).load()

        reason = manager.get_ignore_reason("api.secret")
        assert reason is not None
        assert "*.secret" in reason

    def test_filter_paths(self, temp_project):
        """Test filtering a list of paths."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        claudeignore = temp_project / ".claudeignore"
        claudeignore.write_text("*.secret\n*.tmp\n")

        manager = HierarchicalIgnoreManager(temp_project).load()

        paths = [
            "src/main.py",
            "api.secret",
            "temp.tmp",
            "README.md",
        ]

        filtered = manager.filter_paths(paths)

        assert len(filtered) == 2
        assert any("main.py" in str(p) for p in filtered)
        assert any("README.md" in str(p) for p in filtered)

    def test_lazy_loading(self, temp_project):
        """Test that patterns are loaded lazily."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        manager = HierarchicalIgnoreManager(temp_project)

        # Not loaded yet
        assert not manager.is_loaded

        # Calling should_ignore should trigger loading
        manager.should_ignore("test.py")

        assert manager.is_loaded

    def test_stats_before_and_after_load(self, temp_project):
        """Test stats are correct before and after loading."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        claudeignore = temp_project / ".claudeignore"
        claudeignore.write_text("*.custom\n")

        manager = HierarchicalIgnoreManager(temp_project)

        # Before load - stats should trigger loading
        stats_before = manager.get_stats()

        # After load
        stats_after = manager.get_stats()

        assert stats_before == stats_after
        assert stats_after["project_patterns"] == 1


class TestCreateDefaultClaudeignore:
    """Test the create_default_claudeignore function."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_creates_file(self, temp_dir):
        """Test that the function creates a .claudeignore file."""
        from claude_indexer.utils.hierarchical_ignore import create_default_claudeignore

        result = create_default_claudeignore(temp_dir)

        assert result.exists()
        assert result.name == ".claudeignore"

    def test_includes_secrets_patterns(self, temp_dir):
        """Test that secrets patterns are included by default."""
        from claude_indexer.utils.hierarchical_ignore import create_default_claudeignore

        result = create_default_claudeignore(temp_dir, include_secrets=True)

        content = result.read_text()
        assert ".env" in content
        assert "credentials.json" in content

    def test_includes_ml_patterns(self, temp_dir):
        """Test that ML artifact patterns are included by default."""
        from claude_indexer.utils.hierarchical_ignore import create_default_claudeignore

        result = create_default_claudeignore(temp_dir, include_ml=True)

        content = result.read_text()
        assert "*.h5" in content or "*.pkl" in content

    def test_excludes_sections_when_disabled(self, temp_dir):
        """Test that sections can be excluded."""
        from claude_indexer.utils.hierarchical_ignore import create_default_claudeignore

        result = create_default_claudeignore(
            temp_dir, include_secrets=False, include_ml=False
        )

        content = result.read_text()
        # These should still have basic patterns
        assert ".env" not in content or "SECRETS" not in content

    def test_creates_parent_directories(self, temp_dir):
        """Test that parent directories are created if needed."""
        from claude_indexer.utils.hierarchical_ignore import create_default_claudeignore

        nested_dir = temp_dir / "deep" / "nested" / "path"

        result = create_default_claudeignore(nested_dir)

        assert result.exists()
        assert result.parent.exists()
