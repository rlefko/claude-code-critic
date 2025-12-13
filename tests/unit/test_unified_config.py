"""Unit tests for the UnifiedConfig model and related classes."""

import pytest
from pydantic import ValidationError

from claude_indexer.config import IndexerConfig
from claude_indexer.config.unified_config import (
    APIConfig,
    EmbeddingConfig,
    FilePatterns,
    GuardConfig,
    HookConfig,
    HooksConfig,
    IndexingConfig,
    LoggingConfig,
    OpenAIConfig,
    PerformanceConfig,
    ProjectInfo,
    QdrantConfig,
    RuleConfig,
    UnifiedConfig,
    VoyageConfig,
    WatcherConfig,
    _deep_merge,
)


class TestAPIConfig:
    """Tests for API configuration models."""

    def test_openai_config_defaults(self):
        """Test OpenAI config default values."""
        config = OpenAIConfig()
        assert config.api_key == ""
        assert config.model == "text-embedding-3-small"

    def test_voyage_config_defaults(self):
        """Test Voyage config default values."""
        config = VoyageConfig()
        assert config.api_key == ""
        assert config.model == "voyage-3.5-lite"

    def test_qdrant_config_defaults(self):
        """Test Qdrant config default values."""
        config = QdrantConfig()
        assert config.url == "http://localhost:6333"
        assert config.api_key == ""

    def test_api_config_nested(self):
        """Test APIConfig with nested configs."""
        config = APIConfig(
            openai=OpenAIConfig(api_key="sk-test"),
            voyage=VoyageConfig(api_key="va-test"),
            qdrant=QdrantConfig(url="https://cloud.qdrant.io"),
        )
        assert config.openai.api_key == "sk-test"
        assert config.voyage.api_key == "va-test"
        assert config.qdrant.url == "https://cloud.qdrant.io"


class TestEmbeddingConfig:
    """Tests for embedding configuration."""

    def test_default_values(self):
        """Test default embedding config values."""
        config = EmbeddingConfig()
        assert config.provider == "voyage"
        assert config.model is None
        assert config.dimension == 512

    def test_dimension_constraints(self):
        """Test dimension value constraints."""
        config = EmbeddingConfig(dimension=256)
        assert config.dimension == 256

        with pytest.raises(ValidationError):
            EmbeddingConfig(dimension=64)  # Below minimum 128

        with pytest.raises(ValidationError):
            EmbeddingConfig(dimension=8192)  # Above maximum 4096


class TestFilePatterns:
    """Tests for file pattern configuration."""

    def test_default_include_patterns(self):
        """Test default include patterns contain expected file types."""
        patterns = FilePatterns()
        assert "*.py" in patterns.include
        assert "*.js" in patterns.include
        assert "*.ts" in patterns.include
        assert "*.md" in patterns.include

    def test_default_exclude_patterns(self):
        """Test default exclude patterns contain expected directories."""
        patterns = FilePatterns()
        assert "node_modules/" in patterns.exclude
        assert ".git/" in patterns.exclude
        assert "__pycache__/" in patterns.exclude
        assert ".venv/" in patterns.exclude

    def test_custom_patterns(self):
        """Test custom include/exclude patterns."""
        patterns = FilePatterns(
            include=["*.py", "*.pyx"],
            exclude=["tests/", "docs/"],
        )
        assert patterns.include == ["*.py", "*.pyx"]
        assert patterns.exclude == ["tests/", "docs/"]


class TestIndexingConfig:
    """Tests for indexing configuration."""

    def test_default_values(self):
        """Test default indexing config values."""
        config = IndexingConfig()
        assert config.enabled is True
        assert config.incremental is True
        assert config.max_file_size == 1048576  # 1MB
        assert config.include_tests is False

    def test_max_file_size_constraint(self):
        """Test max file size minimum constraint."""
        config = IndexingConfig(max_file_size=2048)
        assert config.max_file_size == 2048

        with pytest.raises(ValidationError):
            IndexingConfig(max_file_size=512)  # Below minimum 1024


class TestWatcherConfig:
    """Tests for watcher configuration."""

    def test_default_values(self):
        """Test default watcher config values."""
        config = WatcherConfig()
        assert config.enabled is True
        assert config.debounce_seconds == 2.0
        assert config.use_gitignore is True

    def test_debounce_constraints(self):
        """Test debounce seconds constraints."""
        config = WatcherConfig(debounce_seconds=1.5)
        assert config.debounce_seconds == 1.5

        with pytest.raises(ValidationError):
            WatcherConfig(debounce_seconds=0.05)  # Below minimum 0.1

        with pytest.raises(ValidationError):
            WatcherConfig(debounce_seconds=120.0)  # Above maximum 60.0


class TestPerformanceConfig:
    """Tests for performance configuration."""

    def test_default_values(self):
        """Test default performance config values."""
        config = PerformanceConfig()
        assert config.batch_size == 100
        assert config.initial_batch_size == 25
        assert config.batch_size_ramp_up is True
        assert config.max_concurrent_files == 5
        assert config.use_parallel_processing is True
        assert config.max_parallel_workers == 0  # Auto

    def test_batch_size_constraints(self):
        """Test batch size constraints."""
        with pytest.raises(ValidationError):
            PerformanceConfig(batch_size=0)  # Below minimum 1

        with pytest.raises(ValidationError):
            PerformanceConfig(batch_size=2000)  # Above maximum 1000


class TestHooksConfig:
    """Tests for hooks configuration."""

    def test_default_values(self):
        """Test default hooks config values."""
        config = HooksConfig()
        assert config.enabled is True
        assert config.post_tool_use == []
        assert config.stop == []
        assert config.session_start == []

    def test_hook_config(self):
        """Test individual hook configuration."""
        hook = HookConfig(
            matcher="Write|Edit",
            command=".claude/hooks/after-write.sh",
        )
        assert hook.matcher == "Write|Edit"
        assert hook.enabled is True
        assert hook.timeout == 30000

    def test_hook_config_validation(self):
        """Test hook config validation."""
        with pytest.raises(ValidationError):
            HookConfig(matcher="", command="cmd")  # Empty matcher

        with pytest.raises(ValidationError):
            HookConfig(matcher="*", command="")  # Empty command


class TestGuardConfig:
    """Tests for guard configuration."""

    def test_default_values(self):
        """Test default guard config values."""
        config = GuardConfig()
        assert config.enabled is True
        assert config.rules == {}
        assert config.severity_thresholds == {"block": "HIGH", "warn": "MEDIUM"}

    def test_rule_config(self):
        """Test individual rule configuration."""
        rule = RuleConfig(
            enabled=True,
            severity="CRITICAL",
            auto_fix=True,
        )
        assert rule.enabled is True
        assert rule.severity == "CRITICAL"
        assert rule.auto_fix is True


class TestLoggingConfig:
    """Tests for logging configuration."""

    def test_default_values(self):
        """Test default logging config values."""
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.verbose is True
        assert config.debug is False
        assert config.log_file is None


class TestProjectInfo:
    """Tests for project info configuration."""

    def test_required_fields(self):
        """Test that name and collection are required."""
        with pytest.raises(ValidationError):
            ProjectInfo()  # Missing required fields

        project = ProjectInfo(name="test", collection="test-collection")
        assert project.name == "test"
        assert project.collection == "test-collection"
        assert project.description == ""
        assert project.project_type == "generic"

    def test_min_length_validation(self):
        """Test minimum length validation."""
        with pytest.raises(ValidationError):
            ProjectInfo(name="", collection="test")  # Empty name


class TestUnifiedConfig:
    """Tests for the main UnifiedConfig model."""

    def test_default_values(self):
        """Test UnifiedConfig default values."""
        config = UnifiedConfig()
        assert config.version == "3.0"
        assert config.project is None
        assert isinstance(config.api, APIConfig)
        assert isinstance(config.embedding, EmbeddingConfig)
        assert isinstance(config.indexing, IndexingConfig)

    def test_full_config_creation(self):
        """Test creating a full configuration."""
        config = UnifiedConfig(
            project=ProjectInfo(name="test-project", collection="test-collection"),
            api=APIConfig(
                openai=OpenAIConfig(api_key="sk-123"),
                voyage=VoyageConfig(api_key="va-456"),
            ),
            embedding=EmbeddingConfig(provider="voyage"),
            logging=LoggingConfig(debug=True),
        )

        assert config.project.name == "test-project"
        assert config.api.openai.api_key == "sk-123"
        assert config.embedding.provider == "voyage"
        assert config.logging.debug is True

    def test_to_indexer_config(self):
        """Test conversion to legacy IndexerConfig."""
        unified = UnifiedConfig(
            project=ProjectInfo(name="test", collection="test-collection"),
            api=APIConfig(
                openai=OpenAIConfig(api_key="sk-test"),
                voyage=VoyageConfig(api_key="va-test", model="voyage-3"),
                qdrant=QdrantConfig(url="https://qdrant.example.com"),
            ),
            embedding=EmbeddingConfig(provider="voyage"),
            watcher=WatcherConfig(debounce_seconds=3.0),
            performance=PerformanceConfig(batch_size=50),
            logging=LoggingConfig(debug=True, verbose=True),
        )

        indexer_config = unified.to_indexer_config()

        assert isinstance(indexer_config, IndexerConfig)
        assert indexer_config.openai_api_key == "sk-test"
        assert indexer_config.voyage_api_key == "va-test"
        assert indexer_config.qdrant_url == "https://qdrant.example.com"
        assert indexer_config.collection_name == "test-collection"
        assert indexer_config.debounce_seconds == 3.0
        assert indexer_config.batch_size == 50
        assert indexer_config.indexer_debug is True

    def test_from_indexer_config(self):
        """Test creation from legacy IndexerConfig."""
        legacy = IndexerConfig(
            openai_api_key="sk-legacy",
            voyage_api_key="va-legacy",
            qdrant_url="https://qdrant.legacy.com",
            collection_name="legacy-collection",
            debounce_seconds=2.5,
            batch_size=75,
            indexer_debug=True,
        )

        unified = UnifiedConfig.from_indexer_config(
            legacy, project_name="legacy-project"
        )

        assert unified.project.name == "legacy-project"
        assert unified.project.collection == "legacy-collection"
        assert unified.api.openai.api_key == "sk-legacy"
        assert unified.api.voyage.api_key == "va-legacy"
        assert unified.watcher.debounce_seconds == 2.5
        assert unified.performance.batch_size == 75
        assert unified.logging.debug is True

    def test_from_dict_v30_format(self):
        """Test creation from v3.0 format dictionary."""
        data = {
            "version": "3.0",
            "project": {"name": "test", "collection": "test-coll"},
            "embedding": {"provider": "openai"},
            "logging": {"debug": True},
        }

        config = UnifiedConfig.from_dict(data)

        assert config.version == "3.0"
        assert config.project.name == "test"
        assert config.embedding.provider == "openai"
        assert config.logging.debug is True

    def test_from_dict_v26_format(self):
        """Test conversion from v2.6 format dictionary."""
        data = {
            "version": "2.6",
            "project": {"name": "legacy", "collection": "legacy-coll"},
            "indexing": {
                "enabled": True,
                "max_file_size": 2097152,
            },
            "watcher": {
                "debounce_seconds": 3.0,
            },
        }

        config = UnifiedConfig.from_dict(data)

        assert config.version == "3.0"  # Converted
        assert config.project.name == "legacy"
        assert config.indexing.max_file_size == 2097152
        assert config.watcher.debounce_seconds == 3.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = UnifiedConfig(
            project=ProjectInfo(name="test", collection="test-coll"),
            logging=LoggingConfig(debug=True),
        )

        d = config.to_dict()

        assert d["version"] == "3.0"
        assert d["project"]["name"] == "test"
        assert d["logging"]["debug"] is True

    def test_to_dict_exclude_defaults(self):
        """Test conversion to dictionary excluding defaults."""
        config = UnifiedConfig(
            project=ProjectInfo(name="test", collection="test-coll"),
        )

        d = config.to_dict(exclude_defaults=True)

        # Should include explicitly set values
        assert "project" in d
        # Should exclude default values (depending on Pydantic behavior)

    def test_get_effective_model_voyage(self):
        """Test getting effective model for Voyage provider."""
        config = UnifiedConfig(
            embedding=EmbeddingConfig(provider="voyage"),
            api=APIConfig(voyage=VoyageConfig(model="voyage-3.5-lite")),
        )

        assert config.get_effective_model() == "voyage-3.5-lite"

    def test_get_effective_model_openai(self):
        """Test getting effective model for OpenAI provider."""
        config = UnifiedConfig(
            embedding=EmbeddingConfig(provider="openai"),
            api=APIConfig(openai=OpenAIConfig(model="text-embedding-3-large")),
        )

        assert config.get_effective_model() == "text-embedding-3-large"

    def test_get_effective_model_override(self):
        """Test getting effective model with explicit override."""
        config = UnifiedConfig(
            embedding=EmbeddingConfig(provider="voyage", model="custom-model"),
        )

        assert config.get_effective_model() == "custom-model"

    def test_get_effective_api_key_voyage(self):
        """Test getting effective API key for Voyage provider."""
        config = UnifiedConfig(
            embedding=EmbeddingConfig(provider="voyage"),
            api=APIConfig(voyage=VoyageConfig(api_key="va-key")),
        )

        assert config.get_effective_api_key() == "va-key"

    def test_get_effective_api_key_openai(self):
        """Test getting effective API key for OpenAI provider."""
        config = UnifiedConfig(
            embedding=EmbeddingConfig(provider="openai"),
            api=APIConfig(openai=OpenAIConfig(api_key="sk-key")),
        )

        assert config.get_effective_api_key() == "sk-key"

    def test_merge_with(self):
        """Test merging two configs."""
        base = UnifiedConfig(
            embedding=EmbeddingConfig(provider="voyage"),
            logging=LoggingConfig(debug=False, verbose=True),
        )

        override = UnifiedConfig(
            logging=LoggingConfig(debug=True),
        )

        merged = base.merge_with(override)

        assert merged.embedding.provider == "voyage"  # From base
        assert merged.logging.debug is True  # From override
        assert merged.logging.verbose is True  # From base (not overridden)


class TestDeepMerge:
    """Tests for the _deep_merge utility function."""

    def test_simple_merge(self):
        """Test simple dictionary merge."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        _deep_merge(base, override)

        assert base == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        """Test nested dictionary merge."""
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 3, "z": 4}}
        _deep_merge(base, override)

        assert base == {"a": {"x": 1, "y": 3, "z": 4}, "b": 3}

    def test_deep_nested_merge(self):
        """Test deeply nested dictionary merge."""
        base = {"a": {"b": {"c": 1}}}
        override = {"a": {"b": {"d": 2}}}
        _deep_merge(base, override)

        assert base == {"a": {"b": {"c": 1, "d": 2}}}

    def test_non_dict_override(self):
        """Test that non-dict values replace rather than merge."""
        base = {"a": {"x": 1}}
        override = {"a": "string"}
        _deep_merge(base, override)

        assert base == {"a": "string"}
