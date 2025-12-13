"""Unified configuration system with hierarchical loading support.

This module provides a unified configuration model that consolidates
all configuration options into a single, well-structured schema.
It maintains backward compatibility with legacy configurations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import IndexerConfig

from pydantic import BaseModel, Field


class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""

    api_key: str = Field(default="", description="OpenAI API key")
    model: str = Field(
        default="text-embedding-3-small", description="OpenAI embedding model"
    )


class VoyageConfig(BaseModel):
    """Voyage AI API configuration."""

    api_key: str = Field(default="", description="Voyage AI API key")
    model: str = Field(default="voyage-3.5-lite", description="Voyage embedding model")


class QdrantConfig(BaseModel):
    """Qdrant vector database configuration."""

    url: str = Field(default="http://localhost:6333", description="Qdrant server URL")
    api_key: str = Field(default="", description="Qdrant API key")


class APIConfig(BaseModel):
    """API configuration for external services."""

    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    voyage: VoyageConfig = Field(default_factory=VoyageConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)


class EmbeddingConfig(BaseModel):
    """Embedding generation configuration."""

    provider: str = Field(default="voyage", description="Embedding provider")
    model: str | None = Field(
        default=None, description="Override model (uses provider default if None)"
    )
    dimension: int = Field(default=512, ge=128, le=4096, description="Vector dimension")


class FilePatterns(BaseModel):
    """File inclusion and exclusion patterns."""

    include: list[str] = Field(
        default_factory=lambda: [
            "*.py",
            "*.js",
            "*.ts",
            "*.jsx",
            "*.tsx",
            "*.json",
            "*.yaml",
            "*.yml",
            "*.html",
            "*.css",
            "*.md",
        ],
        description="Glob patterns to include",
    )
    exclude: list[str] = Field(
        default_factory=lambda: [
            "*.pyc",
            "__pycache__/",
            ".git/",
            ".venv/",
            "node_modules/",
            "dist/",
            "build/",
            "*.min.js",
            ".env",
            "*.log",
            "logs/",
            ".mypy_cache/",
            ".pytest_cache/",
            ".tox/",
            ".coverage",
            "htmlcov/",
            "coverage/",
            ".cache/",
            "test-results/",
            "playwright-report/",
            ".idea/",
            ".vscode/",
            ".zed/",
            ".DS_Store",
            ".npm/",
            ".next/",
            ".parcel-cache/",
            "*.tsbuildinfo",
            "*.map",
            "*.db",
            "*.sqlite3",
            "chroma_db/",
            "*.tmp",
            "*.bak",
            "*.old",
            "debug/",
            "qdrant_storage/",
            "backups/",
            "*.egg-info",
            "settings.txt",
            ".claude-indexer/",
            ".claude/",
            "package-lock.json",
            ".index_cache/",
            ".embedding_cache/",
            "isolated_test/",
            "*_file_hashes.json",
        ],
        description="Glob patterns to exclude",
    )


class ParserSpecificConfig(BaseModel):
    """Base parser-specific configuration."""

    enabled: bool = Field(default=True, description="Enable this parser")

    class Config:
        extra = "allow"


class IndexingConfig(BaseModel):
    """Indexing behavior configuration."""

    enabled: bool = Field(default=True, description="Enable automatic indexing")
    incremental: bool = Field(
        default=True, description="Use incremental indexing (only changed files)"
    )
    file_patterns: FilePatterns = Field(default_factory=FilePatterns)
    max_file_size: int = Field(
        default=1048576, ge=1024, description="Maximum file size in bytes"
    )
    include_tests: bool = Field(
        default=False, description="Include test files in the index"
    )
    parser_config: dict[str, ParserSpecificConfig | dict[str, Any]] = Field(
        default_factory=dict, description="Parser-specific configuration"
    )


class WatcherConfig(BaseModel):
    """File watcher configuration."""

    enabled: bool = Field(default=True, description="Enable file watching")
    debounce_seconds: float = Field(
        default=2.0, ge=0.1, le=60.0, description="Debounce delay in seconds"
    )
    use_gitignore: bool = Field(default=True, description="Respect .gitignore patterns")


class PerformanceConfig(BaseModel):
    """Performance tuning settings."""

    batch_size: int = Field(
        default=100, ge=1, le=1000, description="Batch size for embedding API calls"
    )
    initial_batch_size: int = Field(
        default=25, ge=1, le=50, description="Initial batch size"
    )
    batch_size_ramp_up: bool = Field(
        default=True, description="Gradually increase batch size"
    )
    max_concurrent_files: int = Field(
        default=5, ge=1, le=100, description="Max concurrent file processing"
    )
    use_parallel_processing: bool = Field(
        default=True, description="Enable multiprocessing"
    )
    max_parallel_workers: int = Field(
        default=0, ge=0, le=16, description="Max parallel workers (0 = auto)"
    )
    cleanup_interval_minutes: int = Field(
        default=1, ge=0, le=10080, description="Cleanup interval (0 = disabled)"
    )


class HookConfig(BaseModel):
    """Individual hook configuration."""

    matcher: str = Field(..., min_length=1, description="Tool pattern to match")
    command: str = Field(..., min_length=1, description="Command to execute")
    enabled: bool = Field(default=True, description="Enable this hook")
    timeout: int = Field(default=30000, ge=1000, description="Timeout in milliseconds")


class HooksConfig(BaseModel):
    """Claude Code hooks configuration."""

    enabled: bool = Field(default=True, description="Enable hook system")
    post_tool_use: list[HookConfig] = Field(
        default_factory=list, description="Hooks after tool use"
    )
    stop: list[HookConfig] = Field(
        default_factory=list, description="Hooks at end of turn"
    )
    session_start: list[HookConfig] = Field(
        default_factory=list, description="Hooks at session start"
    )


class RuleConfig(BaseModel):
    """Individual rule configuration."""

    enabled: bool = Field(default=True, description="Enable this rule")
    severity: str = Field(default="MEDIUM", description="Rule severity")
    threshold: float | None = Field(default=None, description="Rule-specific threshold")
    auto_fix: bool = Field(default=False, description="Enable auto-fix if supported")


class GuardConfig(BaseModel):
    """Quality guard configuration."""

    enabled: bool = Field(default=True, description="Enable quality guard")
    rules: dict[str, RuleConfig] = Field(
        default_factory=dict, description="Rule-specific configuration"
    )
    severity_thresholds: dict[str, str] = Field(
        default_factory=lambda: {"block": "HIGH", "warn": "MEDIUM"},
        description="Severity thresholds",
    )


class LoggingConfig(BaseModel):
    """Enhanced logging configuration for Milestone 0.3."""

    level: str = Field(
        default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)"
    )
    verbose: bool = Field(default=True, description="Enable verbose output")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_file: str | None = Field(default=None, description="Path to log file")
    # New fields for Milestone 0.3
    format: str = Field(
        default="text",
        description="Log format: 'text' or 'json'",
    )
    rotation_count: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of backup log files (default 3)",
    )
    max_bytes: int = Field(
        default=10485760,
        ge=1048576,
        description="Max log file size in bytes (default 10MB)",
    )
    enable_performance_logging: bool = Field(
        default=False,
        description="Enable performance timing logs",
    )
    enable_multi_component: bool = Field(
        default=False,
        description="Enable category-specific log files",
    )


class ProjectInfo(BaseModel):
    """Project identification and metadata."""

    name: str = Field(..., min_length=1, description="Project name")
    collection: str = Field(..., min_length=1, description="Qdrant collection name")
    description: str = Field(default="", description="Project description")
    project_type: str = Field(default="generic", description="Project type")


class UnifiedConfig(BaseModel):
    """Complete unified configuration.

    This is the main configuration model that consolidates all settings
    into a single, well-structured schema with hierarchical loading support.
    """

    version: str = Field(default="3.0", description="Configuration schema version")
    project: ProjectInfo | None = Field(default=None, description="Project metadata")
    api: APIConfig = Field(default_factory=APIConfig, description="API configuration")
    embedding: EmbeddingConfig = Field(
        default_factory=EmbeddingConfig, description="Embedding configuration"
    )
    indexing: IndexingConfig = Field(
        default_factory=IndexingConfig, description="Indexing configuration"
    )
    watcher: WatcherConfig = Field(
        default_factory=WatcherConfig, description="Watcher configuration"
    )
    performance: PerformanceConfig = Field(
        default_factory=PerformanceConfig, description="Performance configuration"
    )
    hooks: HooksConfig = Field(
        default_factory=HooksConfig, description="Hooks configuration"
    )
    guard: GuardConfig = Field(
        default_factory=GuardConfig, description="Guard configuration"
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig, description="Logging configuration"
    )

    class Config:
        extra = "allow"

    def to_indexer_config(self) -> IndexerConfig:
        """Convert to legacy IndexerConfig for backward compatibility.

        Returns:
            IndexerConfig instance with values from this unified config.
        """
        from .models import IndexerConfig

        return IndexerConfig(
            openai_api_key=self.api.openai.api_key,
            voyage_api_key=self.api.voyage.api_key,
            qdrant_api_key=self.api.qdrant.api_key or "default-key",
            qdrant_url=self.api.qdrant.url,
            embedding_provider=self.embedding.provider,
            embedder_type=self.embedding.provider,
            voyage_model=self.api.voyage.model,
            collection_name=self.project.collection if self.project else "default",
            indexer_debug=self.logging.debug,
            indexer_verbose=self.logging.verbose,
            debounce_seconds=self.watcher.debounce_seconds,
            include_patterns=self.indexing.file_patterns.include,
            exclude_patterns=self.indexing.file_patterns.exclude,
            include_tests=self.indexing.include_tests,
            max_file_size=self.indexing.max_file_size,
            batch_size=self.performance.batch_size,
            initial_batch_size=self.performance.initial_batch_size,
            batch_size_ramp_up=self.performance.batch_size_ramp_up,
            max_concurrent_files=self.performance.max_concurrent_files,
            use_parallel_processing=self.performance.use_parallel_processing,
            max_parallel_workers=self.performance.max_parallel_workers,
            cleanup_interval_minutes=self.performance.cleanup_interval_minutes,
        )

    @classmethod
    def from_indexer_config(
        cls, config: IndexerConfig, project_name: str = "default"
    ) -> UnifiedConfig:
        """Create UnifiedConfig from legacy IndexerConfig.

        Args:
            config: Legacy IndexerConfig instance.
            project_name: Project name to use.

        Returns:
            UnifiedConfig instance with values from the legacy config.
        """
        return cls(
            project=ProjectInfo(
                name=project_name,
                collection=config.collection_name,
            ),
            api=APIConfig(
                openai=OpenAIConfig(api_key=config.openai_api_key),
                voyage=VoyageConfig(
                    api_key=config.voyage_api_key,
                    model=config.voyage_model,
                ),
                qdrant=QdrantConfig(
                    url=config.qdrant_url,
                    api_key=config.qdrant_api_key,
                ),
            ),
            embedding=EmbeddingConfig(
                provider=config.embedding_provider,
            ),
            indexing=IndexingConfig(
                file_patterns=FilePatterns(
                    include=list(config.include_patterns),
                    exclude=list(config.exclude_patterns),
                ),
                max_file_size=config.max_file_size,
                include_tests=config.include_tests,
            ),
            watcher=WatcherConfig(
                debounce_seconds=config.debounce_seconds,
            ),
            performance=PerformanceConfig(
                batch_size=config.batch_size,
                initial_batch_size=config.initial_batch_size,
                batch_size_ramp_up=config.batch_size_ramp_up,
                max_concurrent_files=config.max_concurrent_files,
                use_parallel_processing=config.use_parallel_processing,
                max_parallel_workers=config.max_parallel_workers,
                cleanup_interval_minutes=config.cleanup_interval_minutes,
            ),
            logging=LoggingConfig(
                debug=config.indexer_debug,
                verbose=config.indexer_verbose,
            ),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnifiedConfig:
        """Create UnifiedConfig from a dictionary.

        Handles both v3.0 format and legacy v2.6 ProjectConfig format.

        Args:
            data: Configuration dictionary.

        Returns:
            UnifiedConfig instance.
        """
        version = data.get("version", "2.6")

        if version >= "3.0":
            return cls(**data)

        # Convert v2.6 format to v3.0
        return cls._from_v26_format(data)

    @classmethod
    def _from_v26_format(cls, data: dict[str, Any]) -> UnifiedConfig:
        """Convert v2.6 ProjectConfig format to v3.0 UnifiedConfig."""
        result: dict[str, Any] = {"version": "3.0"}

        # Project info
        if "project" in data:
            project = data["project"]
            result["project"] = {
                "name": project.get("name", "unnamed"),
                "collection": project.get("collection", "default"),
                "description": project.get("description", ""),
            }

        # Indexing config
        if "indexing" in data:
            idx = data["indexing"]
            result["indexing"] = {
                "enabled": idx.get("enabled", True),
                "incremental": idx.get("incremental", True),
                "max_file_size": idx.get("max_file_size", 1048576),
            }
            if "file_patterns" in idx:
                result["indexing"]["file_patterns"] = {
                    "include": idx["file_patterns"].get("include", []),
                    "exclude": idx["file_patterns"].get("exclude", []),
                }
            if "parser_config" in idx:
                result["indexing"]["parser_config"] = idx["parser_config"]

        # Watcher config
        if "watcher" in data:
            watcher = data["watcher"]
            result["watcher"] = {
                "enabled": watcher.get("enabled", True),
                "debounce_seconds": watcher.get("debounce_seconds", 2.0),
                "use_gitignore": watcher.get("use_gitignore", True),
            }

        return cls(**result)

    def to_dict(self, exclude_defaults: bool = False) -> dict[str, Any]:
        """Convert to dictionary representation.

        Args:
            exclude_defaults: If True, exclude fields with default values.

        Returns:
            Dictionary representation of the configuration.
        """
        if exclude_defaults:
            return self.dict(exclude_unset=True, exclude_none=True)
        return self.dict()

    def get_effective_model(self) -> str:
        """Get the effective embedding model based on provider.

        Returns:
            The embedding model to use.
        """
        if self.embedding.model:
            return self.embedding.model

        if self.embedding.provider == "openai":
            return self.api.openai.model
        return self.api.voyage.model

    def get_effective_api_key(self) -> str:
        """Get the effective API key based on provider.

        Returns:
            The API key for the configured provider.
        """
        if self.embedding.provider == "openai":
            return self.api.openai.api_key
        return self.api.voyage.api_key

    def merge_with(self, other: UnifiedConfig) -> UnifiedConfig:
        """Create a new config by merging this config with another.

        The other config's values take precedence.

        Args:
            other: Another UnifiedConfig to merge.

        Returns:
            New UnifiedConfig with merged values.
        """
        base_dict = self.dict()
        other_dict = other.dict(exclude_unset=True, exclude_none=True)
        _deep_merge(base_dict, other_dict)
        return UnifiedConfig(**base_dict)


def _deep_merge(base: dict, override: dict) -> None:
    """Deep merge override into base dict (mutates base).

    Args:
        base: Base dictionary to merge into.
        override: Dictionary with override values.
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
