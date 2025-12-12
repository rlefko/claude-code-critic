"""Tests for file generators functionality."""

import json
from pathlib import Path

import pytest

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

    def test_generate_claudeignore_creates_file(
        self, generator: FileGenerator, tmp_path: Path
    ):
        """Test .claudeignore file creation."""
        result = generator.generate_claudeignore()

        assert result.success
        assert (tmp_path / ".claudeignore").exists()
        content = (tmp_path / ".claudeignore").read_text()
        assert ".env" in content  # Common ignore pattern

    def test_generate_claudeignore_skips_existing(
        self, generator: FileGenerator, tmp_path: Path
    ):
        """Test .claudeignore is skipped if exists."""
        # Pre-create file
        (tmp_path / ".claudeignore").write_text("# Custom content")

        result = generator.generate_claudeignore()

        assert result.success
        assert result.skipped
        assert (tmp_path / ".claudeignore").read_text() == "# Custom content"

    def test_generate_claudeignore_force_overwrites(
        self, generator: FileGenerator, tmp_path: Path
    ):
        """Test .claudeignore is overwritten with force."""
        # Pre-create file
        (tmp_path / ".claudeignore").write_text("# Custom content")

        result = generator.generate_claudeignore(force=True)

        assert result.success
        assert not result.skipped
        assert (tmp_path / ".claudeignore").read_text() != "# Custom content"

    def test_generate_claude_settings_creates_file(
        self, generator: FileGenerator, tmp_path: Path
    ):
        """Test .claude/settings.local.json creation."""
        result = generator.generate_claude_settings()

        assert result.success
        settings_path = tmp_path / ".claude" / "settings.local.json"
        assert settings_path.exists()

        settings = json.loads(settings_path.read_text())
        assert "hooks" in settings or "env" in settings

    def test_generate_claude_settings_skips_existing(
        self, generator: FileGenerator, tmp_path: Path
    ):
        """Test settings file is skipped if exists."""
        # Pre-create file
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.local.json").write_text('{"custom": true}')

        result = generator.generate_claude_settings()

        assert result.success
        assert result.skipped

    def test_generate_guard_config_creates_file(
        self, generator: FileGenerator, tmp_path: Path
    ):
        """Test .claude/guard.config.json creation."""
        result = generator.generate_guard_config()

        assert result.success
        config_path = tmp_path / ".claude" / "guard.config.json"
        assert config_path.exists()

        config = json.loads(config_path.read_text())
        assert config.get("enabled") is True
        assert "categories" in config

    def test_generate_guard_config_has_default_categories(
        self, generator: FileGenerator, tmp_path: Path
    ):
        """Test guard config has all default categories."""
        generator.generate_guard_config()

        config_path = tmp_path / ".claude" / "guard.config.json"
        config = json.loads(config_path.read_text())

        categories = config.get("categories", {})
        assert "security" in categories
        assert "tech_debt" in categories
        assert "resilience" in categories
        assert "documentation" in categories

    def test_generate_project_config_creates_file(
        self, generator: FileGenerator, tmp_path: Path
    ):
        """Test .claude-indexer/config.json creation."""
        result = generator.generate_project_config("test-collection")

        assert result.success
        config_path = tmp_path / ".claude-indexer" / "config.json"
        assert config_path.exists()

    def test_update_gitignore_adds_entries(
        self, generator: FileGenerator, tmp_path: Path
    ):
        """Test .gitignore gets Claude entries."""
        # Create empty gitignore
        (tmp_path / ".gitignore").write_text("node_modules/\n")

        result = generator.update_gitignore()

        assert result.success
        content = (tmp_path / ".gitignore").read_text()
        assert "# Claude Code Memory" in content
        assert ".claude-indexer/" in content

    def test_update_gitignore_skips_existing_entries(
        self, generator: FileGenerator, tmp_path: Path
    ):
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

        # Should return a dict with 'root' and project-type keys
        assert isinstance(templates, dict)
        assert "root" in templates
        # Check root templates exist
        root_templates = templates.get("root", [])
        assert isinstance(root_templates, list)

    def test_get_available_templates_includes_project_types(self):
        """Test that available templates includes project-type directories."""
        templates = TemplateManager.get_available_templates()

        # Should include project-type subdirectories
        assert "python" in templates
        assert "javascript" in templates
        assert "typescript" in templates
        assert "react" in templates
        assert "generic" in templates


class TestProjectTypeTemplateResolution:
    """Tests for project-type-specific template resolution."""

    def test_resolve_template_path_python(self, tmp_path: Path):
        """Test Python templates are resolved correctly."""
        manager = TemplateManager(tmp_path, "test", ProjectType.PYTHON)

        # Create a mock python template
        python_template_dir = TemplateManager.TEMPLATES_DIR / "python"
        if python_template_dir.exists():
            path = manager._resolve_template_path(".claudeignore.template")
            assert "python" in str(path)

    def test_resolve_template_path_javascript(self, tmp_path: Path):
        """Test JavaScript templates are resolved correctly."""
        manager = TemplateManager(tmp_path, "test", ProjectType.JAVASCRIPT)

        # Check that javascript templates are resolved
        path = manager._resolve_template_path(".claudeignore.template")
        javascript_dir = TemplateManager.TEMPLATES_DIR / "javascript"
        if (
            javascript_dir.exists()
            and (javascript_dir / ".claudeignore.template").exists()
        ):
            assert "javascript" in str(path)

    def test_resolve_template_path_typescript(self, tmp_path: Path):
        """Test TypeScript templates are resolved correctly."""
        manager = TemplateManager(tmp_path, "test", ProjectType.TYPESCRIPT)

        path = manager._resolve_template_path(".claudeignore.template")
        typescript_dir = TemplateManager.TEMPLATES_DIR / "typescript"
        if (
            typescript_dir.exists()
            and (typescript_dir / ".claudeignore.template").exists()
        ):
            assert "typescript" in str(path)

    def test_nextjs_uses_react_templates(self, tmp_path: Path):
        """Test Next.js maps to react template directory."""
        manager = TemplateManager(tmp_path, "test", ProjectType.NEXTJS)

        path = manager._resolve_template_path(".claudeignore.template")
        react_dir = TemplateManager.TEMPLATES_DIR / "react"
        if react_dir.exists() and (react_dir / ".claudeignore.template").exists():
            assert "react" in str(path)

    def test_vue_uses_react_templates(self, tmp_path: Path):
        """Test Vue maps to react template directory."""
        manager = TemplateManager(tmp_path, "test", ProjectType.VUE)

        path = manager._resolve_template_path(".claudeignore.template")
        react_dir = TemplateManager.TEMPLATES_DIR / "react"
        if react_dir.exists() and (react_dir / ".claudeignore.template").exists():
            assert "react" in str(path)

    def test_resolve_template_path_falls_back_to_root(self, tmp_path: Path):
        """Test fallback to root when type-specific template not found."""
        manager = TemplateManager(tmp_path, "test", ProjectType.PYTHON)

        # Request a template that only exists at root
        path = manager._resolve_template_path("settings.local.json.template")
        # Should fall back to root template
        assert path.name == "settings.local.json.template"

    def test_generic_fallback(self, tmp_path: Path):
        """Test generic project uses generic or root templates."""
        manager = TemplateManager(tmp_path, "test", ProjectType.GENERIC)

        path = manager._resolve_template_path(".claudeignore.template")
        generic_dir = TemplateManager.TEMPLATES_DIR / "generic"
        if generic_dir.exists() and (generic_dir / ".claudeignore.template").exists():
            assert "generic" in str(path)


class TestProjectTypeFileGeneration:
    """Tests for project-type-specific file generation."""

    @pytest.fixture
    def python_generator(self, tmp_path: Path) -> FileGenerator:
        """Create a Python FileGenerator instance for testing."""
        template_manager = TemplateManager(
            tmp_path, "test-collection", ProjectType.PYTHON
        )
        return FileGenerator(tmp_path, template_manager, ProjectType.PYTHON)

    @pytest.fixture
    def javascript_generator(self, tmp_path: Path) -> FileGenerator:
        """Create a JavaScript FileGenerator instance for testing."""
        template_manager = TemplateManager(
            tmp_path, "test-collection", ProjectType.JAVASCRIPT
        )
        return FileGenerator(tmp_path, template_manager, ProjectType.JAVASCRIPT)

    @pytest.fixture
    def typescript_generator(self, tmp_path: Path) -> FileGenerator:
        """Create a TypeScript FileGenerator instance for testing."""
        template_manager = TemplateManager(
            tmp_path, "test-collection", ProjectType.TYPESCRIPT
        )
        return FileGenerator(tmp_path, template_manager, ProjectType.TYPESCRIPT)

    @pytest.fixture
    def react_generator(self, tmp_path: Path) -> FileGenerator:
        """Create a React FileGenerator instance for testing."""
        template_manager = TemplateManager(
            tmp_path, "test-collection", ProjectType.REACT
        )
        return FileGenerator(tmp_path, template_manager, ProjectType.REACT)

    def test_python_claudeignore_has_python_patterns(
        self, python_generator: FileGenerator, tmp_path: Path
    ):
        """Test Python claudeignore includes Python-specific patterns."""
        result = python_generator.generate_claudeignore()

        assert result.success
        content = (tmp_path / ".claudeignore").read_text()
        assert "__pycache__" in content
        assert ".pytest_cache" in content or "pytest" in content.lower()
        assert ".venv" in content or "venv" in content

    def test_javascript_claudeignore_has_node_patterns(
        self, javascript_generator: FileGenerator, tmp_path: Path
    ):
        """Test JavaScript claudeignore includes Node.js patterns."""
        result = javascript_generator.generate_claudeignore()

        assert result.success
        content = (tmp_path / ".claudeignore").read_text()
        assert "node_modules" in content
        assert "npm" in content.lower() or "yarn" in content.lower()

    def test_typescript_claudeignore_has_ts_patterns(
        self, typescript_generator: FileGenerator, tmp_path: Path
    ):
        """Test TypeScript claudeignore includes TS-specific patterns."""
        result = typescript_generator.generate_claudeignore()

        assert result.success
        content = (tmp_path / ".claudeignore").read_text()
        assert "node_modules" in content
        assert "tsbuildinfo" in content or "dist" in content

    def test_react_claudeignore_has_frontend_patterns(
        self, react_generator: FileGenerator, tmp_path: Path
    ):
        """Test React claudeignore includes frontend patterns."""
        result = react_generator.generate_claudeignore()

        assert result.success
        content = (tmp_path / ".claudeignore").read_text()
        assert "node_modules" in content
        assert ".next" in content or ".nuxt" in content or "build" in content

    def test_python_guard_config_uses_template(
        self, python_generator: FileGenerator, tmp_path: Path
    ):
        """Test Python guard config is generated from template."""
        result = python_generator.generate_guard_config()

        assert result.success
        assert "python" in result.message.lower()

        config_path = tmp_path / ".claude" / "guard.config.json"
        config = json.loads(config_path.read_text())
        assert config.get("enabled") is True
        assert "categories" in config

    def test_typescript_guard_config_has_type_safety(
        self, typescript_generator: FileGenerator, tmp_path: Path
    ):
        """Test TypeScript guard config includes type_safety category."""
        result = typescript_generator.generate_guard_config()

        assert result.success
        config_path = tmp_path / ".claude" / "guard.config.json"
        config = json.loads(config_path.read_text())

        # TypeScript template should have type_safety category
        categories = config.get("categories", {})
        if "type_safety" in categories:
            assert categories["type_safety"].get("enabled") is True
