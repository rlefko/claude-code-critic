"""Tests for file generators functionality."""

import json
import pytest
from pathlib import Path

from claude_indexer.init.generators import FileGenerator
from claude_indexer.init.templates import TemplateManager
from claude_indexer.init.types import ProjectType


class TestFileGenerator:
    """Tests for FileGenerator class."""

    @pytest.fixture
    def generator(self, tmp_path: Path) -> FileGenerator:
        """Create a FileGenerator instance for testing."""
        template_manager = TemplateManager(
            tmp_path, "test-collection", ProjectType.PYTHON
        )
        return FileGenerator(tmp_path, template_manager, ProjectType.PYTHON)

    def test_generate_claudeignore_creates_file(self, generator: FileGenerator, tmp_path: Path):
        """Test .claudeignore file creation."""
        result = generator.generate_claudeignore()

        assert result.success
        assert (tmp_path / ".claudeignore").exists()
        content = (tmp_path / ".claudeignore").read_text()
        assert ".env" in content  # Common ignore pattern

    def test_generate_claudeignore_skips_existing(self, generator: FileGenerator, tmp_path: Path):
        """Test .claudeignore is skipped if exists."""
        # Pre-create file
        (tmp_path / ".claudeignore").write_text("# Custom content")

        result = generator.generate_claudeignore()

        assert result.success
        assert result.skipped
        assert (tmp_path / ".claudeignore").read_text() == "# Custom content"

    def test_generate_claudeignore_force_overwrites(self, generator: FileGenerator, tmp_path: Path):
        """Test .claudeignore is overwritten with force."""
        # Pre-create file
        (tmp_path / ".claudeignore").write_text("# Custom content")

        result = generator.generate_claudeignore(force=True)

        assert result.success
        assert not result.skipped
        assert (tmp_path / ".claudeignore").read_text() != "# Custom content"

    def test_generate_claude_settings_creates_file(self, generator: FileGenerator, tmp_path: Path):
        """Test .claude/settings.local.json creation."""
        result = generator.generate_claude_settings()

        assert result.success
        settings_path = tmp_path / ".claude" / "settings.local.json"
        assert settings_path.exists()

        settings = json.loads(settings_path.read_text())
        assert "hooks" in settings or "env" in settings

    def test_generate_claude_settings_skips_existing(self, generator: FileGenerator, tmp_path: Path):
        """Test settings file is skipped if exists."""
        # Pre-create file
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.local.json").write_text('{"custom": true}')

        result = generator.generate_claude_settings()

        assert result.success
        assert result.skipped

    def test_generate_guard_config_creates_file(self, generator: FileGenerator, tmp_path: Path):
        """Test .claude/guard.config.json creation."""
        result = generator.generate_guard_config()

        assert result.success
        config_path = tmp_path / ".claude" / "guard.config.json"
        assert config_path.exists()

        config = json.loads(config_path.read_text())
        assert config.get("enabled") is True
        assert "categories" in config

    def test_generate_guard_config_has_default_categories(self, generator: FileGenerator, tmp_path: Path):
        """Test guard config has all default categories."""
        generator.generate_guard_config()

        config_path = tmp_path / ".claude" / "guard.config.json"
        config = json.loads(config_path.read_text())

        categories = config.get("categories", {})
        assert "security" in categories
        assert "tech_debt" in categories
        assert "resilience" in categories
        assert "documentation" in categories

    def test_generate_project_config_creates_file(self, generator: FileGenerator, tmp_path: Path):
        """Test .claude-indexer/config.json creation."""
        result = generator.generate_project_config("test-collection")

        assert result.success
        config_path = tmp_path / ".claude-indexer" / "config.json"
        assert config_path.exists()

    def test_update_gitignore_adds_entries(self, generator: FileGenerator, tmp_path: Path):
        """Test .gitignore gets Claude entries."""
        # Create empty gitignore
        (tmp_path / ".gitignore").write_text("node_modules/\n")

        result = generator.update_gitignore()

        assert result.success
        content = (tmp_path / ".gitignore").read_text()
        assert "# Claude Code Memory" in content
        assert ".claude-indexer/" in content

    def test_update_gitignore_skips_existing_entries(self, generator: FileGenerator, tmp_path: Path):
        """Test .gitignore skips if entries exist."""
        # Pre-create with Claude entries
        original = "# Claude Code Memory\n.claude-indexer/\n.mcp.json\n"
        (tmp_path / ".gitignore").write_text(original)

        result = generator.update_gitignore()

        # Should still succeed but might mark some as skipped
        assert result.success

    def test_ensure_claude_directory(self, generator: FileGenerator, tmp_path: Path):
        """Test .claude directory creation."""
        result = generator.ensure_claude_directory()

        assert result.success
        assert (tmp_path / ".claude").is_dir()
        assert (tmp_path / ".claude" / "hooks").is_dir()


class TestTemplateManager:
    """Tests for TemplateManager class."""

    def test_build_variables(self, tmp_path: Path):
        """Test template variables are built correctly."""
        manager = TemplateManager(tmp_path, "test-collection", ProjectType.PYTHON)

        assert manager.variables["PROJECT_NAME"] == tmp_path.name
        assert manager.variables["COLLECTION_NAME"] == "test-collection"
        assert manager.variables["PROJECT_TYPE"] == "python"
        assert "HOOKS_PATH" in manager.variables

    def test_process_template_substitutes_variables(self, tmp_path: Path):
        """Test template variable substitution."""
        manager = TemplateManager(tmp_path, "my-project", ProjectType.PYTHON)

        template = "Collection: {{COLLECTION_NAME}}, Type: {{PROJECT_TYPE}}"
        result = manager.process_template(template)

        assert result == "Collection: my-project, Type: python"

    def test_process_template_handles_spaces(self, tmp_path: Path):
        """Test template handles {{ VAR }} format."""
        manager = TemplateManager(tmp_path, "my-project", ProjectType.PYTHON)

        template = "Collection: {{ COLLECTION_NAME }}"
        result = manager.process_template(template)

        assert result == "Collection: my-project"

    def test_add_variable(self, tmp_path: Path):
        """Test adding custom variables."""
        manager = TemplateManager(tmp_path, "test", ProjectType.PYTHON)
        manager.add_variable("CUSTOM_VAR", "custom_value")

        template = "Custom: {{CUSTOM_VAR}}"
        result = manager.process_template(template)

        assert result == "Custom: custom_value"

    def test_get_available_templates(self):
        """Test getting list of available templates."""
        templates = TemplateManager.get_available_templates()

        # Should find the template files
        assert isinstance(templates, list)
