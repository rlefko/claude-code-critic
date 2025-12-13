"""Unit tests for the HierarchicalConfigLoader."""

import json
from pathlib import Path

from claude_indexer.config.hierarchical_loader import (
    ConfigPaths,
    HierarchicalConfigLoader,
    load_unified_config,
)
from claude_indexer.config.unified_config import UnifiedConfig


class TestConfigPaths:
    """Tests for ConfigPaths class."""

    def test_global_paths(self):
        """Test global configuration paths."""
        assert Path.home() / ".claude-indexer" == ConfigPaths.GLOBAL_DIR
        assert (
            Path.home() / ".claude-indexer" / "config.json" == ConfigPaths.GLOBAL_CONFIG
        )

    def test_project_paths(self):
        """Test project configuration path constants."""
        assert ConfigPaths.PROJECT_DIR == ".claude"
        assert ConfigPaths.PROJECT_SETTINGS == "settings.json"
        assert ConfigPaths.PROJECT_LOCAL == "settings.local.json"
        assert ConfigPaths.LEGACY_PROJECT_DIR == ".claude-indexer"

    def test_get_project_config_dir_new_exists(self, tmp_path):
        """Test get_project_config_dir when new .claude exists."""
        new_dir = tmp_path / ".claude"
        new_dir.mkdir()

        result = ConfigPaths.get_project_config_dir(tmp_path)
        assert result == new_dir

    def test_get_project_config_dir_legacy_exists(self, tmp_path):
        """Test get_project_config_dir when only legacy .claude-indexer exists."""
        legacy_dir = tmp_path / ".claude-indexer"
        legacy_dir.mkdir()

        result = ConfigPaths.get_project_config_dir(tmp_path)
        assert result == legacy_dir

    def test_get_project_config_dir_both_exist(self, tmp_path):
        """Test get_project_config_dir prefers new when both exist."""
        new_dir = tmp_path / ".claude"
        new_dir.mkdir()
        legacy_dir = tmp_path / ".claude-indexer"
        legacy_dir.mkdir()

        result = ConfigPaths.get_project_config_dir(tmp_path, prefer_new=True)
        assert result == new_dir

    def test_get_project_config_dir_none_exist(self, tmp_path):
        """Test get_project_config_dir defaults to new location."""
        result = ConfigPaths.get_project_config_dir(tmp_path)
        assert result == tmp_path / ".claude"

    def test_find_project_config_new_location(self, tmp_path):
        """Test find_project_config finds config in new location."""
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        config_file.write_text('{"version": "3.0"}')

        result = ConfigPaths.find_project_config(tmp_path)
        assert result == config_file

    def test_find_project_config_legacy_location(self, tmp_path):
        """Test find_project_config finds config in legacy location."""
        config_dir = tmp_path / ".claude-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text('{"version": "2.6"}')

        result = ConfigPaths.find_project_config(tmp_path)
        assert result == config_file

    def test_find_project_config_new_takes_precedence(self, tmp_path):
        """Test find_project_config prefers new over legacy."""
        # Create both
        new_dir = tmp_path / ".claude"
        new_dir.mkdir()
        new_config = new_dir / "settings.json"
        new_config.write_text('{"version": "3.0"}')

        legacy_dir = tmp_path / ".claude-indexer"
        legacy_dir.mkdir()
        legacy_config = legacy_dir / "config.json"
        legacy_config.write_text('{"version": "2.6"}')

        result = ConfigPaths.find_project_config(tmp_path)
        assert result == new_config

    def test_find_project_config_none_found(self, tmp_path):
        """Test find_project_config returns None when no config exists."""
        result = ConfigPaths.find_project_config(tmp_path)
        assert result is None


class TestHierarchicalConfigLoader:
    """Tests for HierarchicalConfigLoader class."""

    def test_load_defaults_only(self, tmp_path):
        """Test loading with no config files returns defaults."""
        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()

        assert isinstance(config, UnifiedConfig)
        assert config.version == "3.0"
        assert config.embedding.provider == "voyage"
        assert config.watcher.debounce_seconds == 2.0

    def test_load_from_project_config(self, tmp_path):
        """Test loading from project config file."""
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        config_file.write_text(
            json.dumps(
                {
                    "version": "3.0",
                    "project": {"name": "test", "collection": "test-collection"},
                    "embedding": {"provider": "openai"},
                    "logging": {"debug": True},
                }
            )
        )

        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()

        assert config.project.name == "test"
        assert config.project.collection == "test-collection"
        assert config.embedding.provider == "openai"
        assert config.logging.debug is True

    def test_load_from_legacy_settings_txt(self, tmp_path, monkeypatch):
        """Test loading from legacy settings.txt."""
        # Clear environment variables that might override settings.txt
        for var in ["OPENAI_API_KEY", "VOYAGE_API_KEY", "QDRANT_URL", "QDRANT_API_KEY"]:
            monkeypatch.delenv(var, raising=False)

        settings_file = tmp_path / "settings.txt"
        settings_file.write_text(
            """
openai_api_key=sk-test123
voyage_api_key=va-test456
qdrant_url=https://test.qdrant.com
debounce_seconds=3.5
batch_size=75
indexer_debug=true
"""
        )

        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()

        assert config.api.openai.api_key == "sk-test123"
        assert config.api.voyage.api_key == "va-test456"
        assert config.api.qdrant.url == "https://test.qdrant.com"
        assert config.watcher.debounce_seconds == 3.5
        assert config.performance.batch_size == 75
        assert config.logging.debug is True

    def test_load_from_local_overrides(self, tmp_path):
        """Test loading local overrides."""
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        # Create main config
        main_config = config_dir / "settings.json"
        main_config.write_text(
            json.dumps(
                {
                    "version": "3.0",
                    "logging": {"debug": False, "verbose": True},
                }
            )
        )

        # Create local overrides
        local_config = config_dir / "settings.local.json"
        local_config.write_text(
            json.dumps(
                {
                    "logging": {"debug": True},
                }
            )
        )

        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()

        # Local override should win
        assert config.logging.debug is True
        # Value from main config should be preserved
        assert config.logging.verbose is True

    def test_load_with_environment_variables(self, tmp_path, monkeypatch):
        """Test environment variables override file config."""
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        config_file.write_text(
            json.dumps(
                {
                    "version": "3.0",
                    "api": {"qdrant": {"url": "https://file.qdrant.com"}},
                }
            )
        )

        monkeypatch.setenv("QDRANT_URL", "https://env.qdrant.com")
        monkeypatch.setenv("CLAUDE_INDEXER_DEBUG", "true")

        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()

        # Environment should override file
        assert config.api.qdrant.url == "https://env.qdrant.com"
        assert config.logging.debug is True

    def test_load_with_explicit_overrides(self, tmp_path):
        """Test explicit overrides have highest priority."""
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        config_file.write_text(
            json.dumps(
                {
                    "version": "3.0",
                    "logging": {"debug": False},
                }
            )
        )

        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load(logging={"debug": True})

        assert config.logging.debug is True

    def test_load_with_dot_notation_overrides(self, tmp_path):
        """Test explicit overrides with dot notation."""
        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load(**{"api.openai.api_key": "sk-override"})

        assert config.api.openai.api_key == "sk-override"

    def test_convert_v26_to_v30(self, tmp_path):
        """Test automatic conversion of v2.6 config to v3.0."""
        config_dir = tmp_path / ".claude-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "version": "2.6",
                    "project": {"name": "legacy", "collection": "legacy-coll"},
                    "indexing": {
                        "enabled": True,
                        "max_file_size": 2097152,
                        "file_patterns": {"include": ["*.py"], "exclude": ["tests/"]},
                    },
                    "watcher": {"debounce_seconds": 3.0},
                }
            )
        )

        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()

        assert config.version == "3.0"  # Should be converted
        assert config.project.name == "legacy"
        assert config.indexing.max_file_size == 2097152
        assert config.watcher.debounce_seconds == 3.0

    def test_get_loaded_sources(self, tmp_path):
        """Test tracking of loaded configuration sources."""
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        config_file.write_text(json.dumps({"version": "3.0"}))

        loader = HierarchicalConfigLoader(tmp_path)
        loader.load()

        sources = loader.get_loaded_sources()
        assert any(".claude/settings.json" in s for s in sources)

    def test_get_loaded_sources_with_overrides(self, tmp_path):
        """Test that explicit overrides are tracked."""
        loader = HierarchicalConfigLoader(tmp_path)
        loader.load(logging={"debug": True})

        sources = loader.get_loaded_sources()
        assert "explicit overrides" in sources

    def test_invalid_json_in_config(self, tmp_path):
        """Test handling of invalid JSON in config file."""
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        config_file.write_text("{invalid json")

        loader = HierarchicalConfigLoader(tmp_path)
        # Should not raise, should fall back to defaults
        config = loader.load()

        assert isinstance(config, UnifiedConfig)

    def test_precedence_order(self, tmp_path, monkeypatch):
        """Test complete precedence order: explicit > env > local > project > legacy."""
        # 1. Create legacy settings.txt
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("debounce_seconds=1.0\nindexer_debug=false")

        # 2. Create project config
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        project_config = config_dir / "settings.json"
        project_config.write_text(
            json.dumps(
                {
                    "version": "3.0",
                    "watcher": {"debounce_seconds": 2.0},
                    "logging": {"debug": False, "verbose": False},
                }
            )
        )

        # 3. Create local overrides
        local_config = config_dir / "settings.local.json"
        local_config.write_text(
            json.dumps(
                {
                    "watcher": {"debounce_seconds": 3.0},
                    "logging": {"verbose": True},
                }
            )
        )

        # 4. Set environment variable
        monkeypatch.setenv("CLAUDE_INDEXER_DEBUG", "true")

        # 5. Load with explicit override
        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load(**{"watcher.debounce_seconds": 4.0})

        # Explicit override wins for debounce_seconds
        assert config.watcher.debounce_seconds == 4.0
        # Environment wins for debug
        assert config.logging.debug is True
        # Local override wins for verbose
        assert config.logging.verbose is True


class TestLoadUnifiedConfigFunction:
    """Tests for the load_unified_config convenience function."""

    def test_load_from_path(self, tmp_path):
        """Test loading config from specified path."""
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        config_file.write_text(
            json.dumps(
                {
                    "version": "3.0",
                    "project": {"name": "test", "collection": "test"},
                }
            )
        )

        config = load_unified_config(tmp_path)

        assert config.project.name == "test"

    def test_load_with_overrides(self, tmp_path):
        """Test loading with explicit overrides."""
        config = load_unified_config(tmp_path, logging={"debug": True})

        assert config.logging.debug is True


class TestValueConversion:
    """Tests for value type conversion in loader."""

    def test_convert_boolean_true(self, tmp_path, monkeypatch):
        """Test conversion of 'true' string to boolean."""
        monkeypatch.setenv("CLAUDE_INDEXER_DEBUG", "true")
        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()
        assert config.logging.debug is True

    def test_convert_boolean_false(self, tmp_path, monkeypatch):
        """Test conversion of 'false' string to boolean."""
        monkeypatch.setenv("CLAUDE_INDEXER_DEBUG", "false")
        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()
        assert config.logging.debug is False

    def test_convert_integer(self, tmp_path):
        """Test conversion of integer strings."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("batch_size=100")

        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()
        assert config.performance.batch_size == 100
        assert isinstance(config.performance.batch_size, int)

    def test_convert_float(self, tmp_path):
        """Test conversion of float strings."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("debounce_seconds=2.5")

        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()
        assert config.watcher.debounce_seconds == 2.5
        assert isinstance(config.watcher.debounce_seconds, float)


class TestLegacyMappings:
    """Tests for legacy settings.txt key mappings."""

    def test_all_legacy_mappings(self, tmp_path, monkeypatch):
        """Test that all legacy mappings work correctly."""
        # Clear environment variables that might override settings.txt
        for var in ["OPENAI_API_KEY", "VOYAGE_API_KEY", "QDRANT_URL", "QDRANT_API_KEY"]:
            monkeypatch.delenv(var, raising=False)

        settings_content = """
openai_api_key=sk-openai
voyage_api_key=va-voyage
qdrant_api_key=qdrant-key
qdrant_url=https://qdrant.test
embedding_provider=openai
voyage_model=voyage-3
indexer_debug=true
indexer_verbose=false
debounce_seconds=2.5
max_file_size=2097152
batch_size=50
max_concurrent_files=8
use_parallel_processing=true
max_parallel_workers=4
cleanup_interval_minutes=5
include_tests=true
"""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text(settings_content)

        loader = HierarchicalConfigLoader(tmp_path)
        config = loader.load()

        assert config.api.openai.api_key == "sk-openai"
        assert config.api.voyage.api_key == "va-voyage"
        assert config.api.qdrant.api_key == "qdrant-key"
        assert config.api.qdrant.url == "https://qdrant.test"
        assert config.embedding.provider == "openai"
        assert config.api.voyage.model == "voyage-3"
        assert config.logging.debug is True
        assert config.logging.verbose is False
        assert config.watcher.debounce_seconds == 2.5
        assert config.indexing.max_file_size == 2097152
        assert config.performance.batch_size == 50
        assert config.performance.max_concurrent_files == 8
        assert config.performance.use_parallel_processing is True
        assert config.performance.max_parallel_workers == 4
        assert config.performance.cleanup_interval_minutes == 5
        assert config.indexing.include_tests is True
