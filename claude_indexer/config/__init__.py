"""Unified configuration package.

This package provides a unified, hierarchical configuration system for claude-indexer.
It supports multiple configuration sources with well-defined precedence rules.

Configuration Precedence (highest to lowest):
1. Explicit overrides
2. Environment variables
3. Local overrides (.claude/settings.local.json)
4. Project config (.claude/settings.json)
5. Global config (~/.claude-indexer/config.json)
6. Legacy settings.txt
7. Defaults
"""

# Main configuration exports
from .config_loader import ConfigLoader, load_config

# Project configuration exports
from .config_schema import (
    FilePatterns,
    IndexingConfig,
    JavaScriptParserConfig,
    JSONParserConfig,
    MarkdownParserConfig,
    ParserConfig,
    ProjectConfig,
    ProjectInfo,
    TextParserConfig,
    WatcherConfig,
    YAMLParserConfig,
)

# Hierarchical loader
from .hierarchical_loader import (
    ConfigPaths,
    HierarchicalConfigLoader,
    load_unified_config,
)
from .legacy import create_default_settings_file, load_legacy_settings

# Migration
from .migration import (
    ConfigMigration,
    MigrationAnalysis,
    MigrationResult,
    analyze_migration,
    perform_migration,
)
from .models import IndexerConfig
from .project_config import ProjectConfigManager

# Unified configuration system (v3.0)
from .unified_config import (
    APIConfig,
    EmbeddingConfig,
)
from .unified_config import FilePatterns as UnifiedFilePatterns
from .unified_config import (
    GuardConfig,
    HookConfig,
    HooksConfig,
)
from .unified_config import IndexingConfig as UnifiedIndexingConfig
from .unified_config import (
    LoggingConfig,
    PerformanceConfig,
)
from .unified_config import ProjectInfo as UnifiedProjectInfo
from .unified_config import (
    RuleConfig,
    UnifiedConfig,
)
from .unified_config import WatcherConfig as UnifiedWatcherConfig

# Validation
from .validation import (
    ConfigError,
    ConfigValidator,
    ValidationResult,
    validate_config_dict,
    validate_config_file,
)

__all__ = [
    # Main configuration (legacy)
    "IndexerConfig",
    "load_config",
    "load_legacy_settings",
    "create_default_settings_file",
    "ConfigLoader",
    # Project configuration (legacy)
    "ProjectConfig",
    "ProjectInfo",
    "IndexingConfig",
    "WatcherConfig",
    "FilePatterns",
    "ParserConfig",
    "JavaScriptParserConfig",
    "JSONParserConfig",
    "TextParserConfig",
    "YAMLParserConfig",
    "MarkdownParserConfig",
    "ProjectConfigManager",
    # Unified configuration (v3.0)
    "UnifiedConfig",
    "APIConfig",
    "EmbeddingConfig",
    "GuardConfig",
    "HookConfig",
    "HooksConfig",
    "LoggingConfig",
    "PerformanceConfig",
    "RuleConfig",
    "UnifiedFilePatterns",
    "UnifiedIndexingConfig",
    "UnifiedProjectInfo",
    "UnifiedWatcherConfig",
    # Hierarchical loader
    "ConfigPaths",
    "HierarchicalConfigLoader",
    "load_unified_config",
    # Validation
    "ConfigError",
    "ConfigValidator",
    "ValidationResult",
    "validate_config_dict",
    "validate_config_file",
    # Migration
    "ConfigMigration",
    "MigrationAnalysis",
    "MigrationResult",
    "analyze_migration",
    "perform_migration",
]
