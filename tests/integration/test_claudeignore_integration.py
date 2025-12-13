"""Integration tests for .claudeignore with the indexer."""

import tempfile
from pathlib import Path

import pytest


class TestClaudeignoreIndexerIntegration:
    """Test .claudeignore integration with the indexer."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project with test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            # Create a basic project structure
            (project / "src").mkdir()
            (project / "src" / "main.py").write_text("def main(): pass")
            (project / "src" / "utils.py").write_text("def util(): pass")

            # Create files that should be ignored
            (project / ".env").write_text("SECRET_KEY=abc123")
            (project / "secrets").mkdir()
            (project / "secrets" / "api_key.txt").write_text("sk-secret")

            # Create a claudeignore
            (project / ".claudeignore").write_text(".env\nsecrets/\n*.secret\n")

            yield project

    def test_hierarchical_manager_respects_claudeignore(self, temp_project):
        """Test that HierarchicalIgnoreManager filters correctly."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        manager = HierarchicalIgnoreManager(temp_project).load()

        # Should ignore
        assert manager.should_ignore(".env")
        assert manager.should_ignore("secrets/api_key.txt")

        # Should include
        assert not manager.should_ignore("src/main.py")
        assert not manager.should_ignore("src/utils.py")

    def test_secrets_never_indexed(self, temp_project):
        """Test that .env and secret files are never indexed."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        manager = HierarchicalIgnoreManager(temp_project).load()

        # List all files in the project
        all_files = list(temp_project.rglob("*"))
        all_files = [f for f in all_files if f.is_file()]

        # Filter using the manager
        included = manager.filter_paths(all_files)

        # Convert to relative paths for easier checking
        included_names = [str(p.relative_to(temp_project)) for p in included]

        # Secrets should not be included
        assert ".env" not in included_names
        assert "secrets/api_key.txt" not in included_names

        # Regular files should be included
        assert "src/main.py" in included_names or any(
            "main.py" in n for n in included_names
        )

    def test_negation_includes_file(self, temp_project):
        """Test that negation patterns include previously excluded files."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        # Update claudeignore with negation
        (temp_project / ".claudeignore").write_text("*.env\n!.env.example\n")

        # Create the example file
        (temp_project / ".env.example").write_text("# Example env file")

        manager = HierarchicalIgnoreManager(temp_project).load()

        # .env should still be ignored
        assert manager.should_ignore(".env")

        # .env.example should NOT be ignored due to negation
        assert not manager.should_ignore(".env.example")

    def test_universal_defaults_applied(self, temp_project):
        """Test that universal defaults are always applied."""
        from claude_indexer.utils.hierarchical_ignore import HierarchicalIgnoreManager

        # Create some files that should be caught by universal defaults
        (temp_project / "node_modules").mkdir()
        (temp_project / "node_modules" / "package.json").write_text("{}")
        (temp_project / "__pycache__").mkdir()
        (temp_project / "__pycache__" / "module.pyc").write_bytes(b"")

        # Even with an empty .claudeignore, universal defaults should apply
        (temp_project / ".claudeignore").write_text("")

        manager = HierarchicalIgnoreManager(temp_project).load()

        assert manager.should_ignore("node_modules/package.json")
        assert manager.should_ignore("__pycache__/module.pyc")


class TestClaudeignoreCLIIntegration:
    """Test .claudeignore CLI commands."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_ignore_list_shows_patterns(self, temp_project):
        """Test that 'ignore list' shows patterns."""
        from click.testing import CliRunner

        from claude_indexer.cli_full import cli

        # Create a claudeignore
        (temp_project / ".claudeignore").write_text("*.log\n*.tmp\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["ignore", "list", "-p", str(temp_project)])

        assert result.exit_code == 0
        assert "*.log" in result.output or "Project patterns" in result.output

    def test_ignore_test_identifies_ignored_file(self, temp_project):
        """Test that 'ignore test' correctly identifies ignored files."""
        from click.testing import CliRunner

        from claude_indexer.cli_full import cli

        (temp_project / ".claudeignore").write_text("*.secret\n")

        runner = CliRunner()
        result = runner.invoke(
            cli, ["ignore", "test", "api.secret", "-p", str(temp_project)]
        )

        assert result.exit_code == 0
        assert "IGNORED" in result.output

    def test_ignore_test_identifies_included_file(self, temp_project):
        """Test that 'ignore test' correctly identifies included files."""
        from click.testing import CliRunner

        from claude_indexer.cli_full import cli

        (temp_project / ".claudeignore").write_text("*.secret\n")

        runner = CliRunner()
        result = runner.invoke(
            cli, ["ignore", "test", "main.py", "-p", str(temp_project)]
        )

        assert result.exit_code == 0
        assert "INCLUDED" in result.output
