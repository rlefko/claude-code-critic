"""Hierarchical configuration loader with precedence rules.

This module implements a configuration loader that merges settings from
multiple sources with well-defined precedence:

1. Explicit overrides (highest priority)
2. Environment variables
3. Local overrides (.claude/settings.local.json)
4. Project config (.claude/settings.json or .claude-indexer/config.json)
5. Global config (~/.claude-indexer/config.json)
6. Legacy settings.txt
7. Defaults (lowest priority)
"""

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..indexer_logging import get_logger
from .legacy import load_legacy_settings
from .unified_config import ProjectInfo, UnifiedConfig, _deep_merge

logger = get_logger()


class ConfigPaths:
    """Standard configuration file paths."""

    # Global config directory
    GLOBAL_DIR = Path.home() / ".claude-indexer"
    GLOBAL_CONFIG = GLOBAL_DIR / "config.json"
    GLOBAL_RULES_DIR = GLOBAL_DIR / "rules"
    GLOBAL_IGNORE = GLOBAL_DIR / ".claudeignore"

    # Legacy project config (for backward compatibility)
    LEGACY_PROJECT_DIR = ".claude-indexer"
    LEGACY_PROJECT_CONFIG = "config.json"

    # New project config location
    PROJECT_DIR = ".claude"
    PROJECT_SETTINGS = "settings.json"
    PROJECT_GUARD = "guard.config.json"
    PROJECT_MEMORY = "memory.config.json"
    PROJECT_IGNORE = ".claudeignore"
    PROJECT_LOCAL = "settings.local.json"

    @classmethod
    def get_project_config_dir(
        cls, project_path: Path, prefer_new: bool = True
    ) -> Path:
        """Get the project configuration directory.

        Checks for both new (.claude) and legacy (.claude-indexer) locations.

        Args:
            project_path: Path to the project root.
            prefer_new: If True, prefer .claude over .claude-indexer if both exist.

        Returns:
            Path to the configuration directory.
        """
        new_dir = project_path / cls.PROJECT_DIR
        legacy_dir = project_path / cls.LEGACY_PROJECT_DIR

        if prefer_new and new_dir.exists():
            return new_dir
        if legacy_dir.exists():
            return legacy_dir
        # Default to new location for new projects
        return new_dir

    @classmethod
    def find_project_config(cls, project_path: Path) -> Path | None:
        """Find the project configuration file.

        Checks new location first, then legacy.

        Args:
            project_path: Path to the project root.

        Returns:
            Path to config file if found, None otherwise.
        """
        # Check new location first
        new_config = project_path / cls.PROJECT_DIR / cls.PROJECT_SETTINGS
        if new_config.exists():
            return new_config

        # Check legacy location
        legacy_config = (
            project_path / cls.LEGACY_PROJECT_DIR / cls.LEGACY_PROJECT_CONFIG
        )
        if legacy_config.exists():
            return legacy_config

        return None


class HierarchicalConfigLoader:
    """Loads configuration with hierarchical precedence.

    Precedence (highest to lowest):
    1. Explicit overrides (passed to load())
    2. Environment variables
    3. Local overrides (.claude/settings.local.json)
    4. Project config (.claude/settings.json or .claude-indexer/config.json)
    5. Global config (~/.claude-indexer/config.json)
    6. Legacy settings.txt
    7. Defaults
    """

    # Environment variable to config path mapping
    ENV_MAPPINGS: dict[str, tuple[str, ...]] = {
        "OPENAI_API_KEY": ("api", "openai", "api_key"),
        "VOYAGE_API_KEY": ("api", "voyage", "api_key"),
        "QDRANT_API_KEY": ("api", "qdrant", "api_key"),
        "QDRANT_URL": ("api", "qdrant", "url"),
        "EMBEDDING_PROVIDER": ("embedding", "provider"),
        "VOYAGE_MODEL": ("api", "voyage", "model"),
        "CLAUDE_INDEXER_DEBUG": ("logging", "debug"),
        "CLAUDE_INDEXER_VERBOSE": ("logging", "verbose"),
        "CLAUDE_INDEXER_COLLECTION": ("project", "collection"),
    }

    # Legacy settings.txt key to config path mapping
    LEGACY_MAPPINGS: dict[str, tuple[str, ...]] = {
        "openai_api_key": ("api", "openai", "api_key"),
        "voyage_api_key": ("api", "voyage", "api_key"),
        "qdrant_api_key": ("api", "qdrant", "api_key"),
        "qdrant_url": ("api", "qdrant", "url"),
        "embedding_provider": ("embedding", "provider"),
        "voyage_model": ("api", "voyage", "model"),
        "indexer_debug": ("logging", "debug"),
        "indexer_verbose": ("logging", "verbose"),
        "debounce_seconds": ("watcher", "debounce_seconds"),
        "max_file_size": ("indexing", "max_file_size"),
        "batch_size": ("performance", "batch_size"),
        "max_concurrent_files": ("performance", "max_concurrent_files"),
        "use_parallel_processing": ("performance", "use_parallel_processing"),
        "max_parallel_workers": ("performance", "max_parallel_workers"),
        "cleanup_interval_minutes": ("performance", "cleanup_interval_minutes"),
        "include_markdown": ("indexing", "include_markdown"),
        "include_tests": ("indexing", "include_tests"),
    }

    def __init__(self, project_path: Path | None = None):
        """Initialize the configuration loader.

        Args:
            project_path: Path to the project root. Defaults to current directory.
        """
        self.project_path = Path(project_path).resolve() if project_path else Path.cwd()
        self._loaded_sources: list[str] = []

    def load(self, **overrides: Any) -> UnifiedConfig:
        """Load unified configuration from all sources.

        Args:
            **overrides: Explicit configuration overrides.

        Returns:
            UnifiedConfig with all sources merged.
        """
        self._loaded_sources = []
        config_dict: dict[str, Any] = {}

        # 1. Load legacy settings.txt (lowest priority after defaults)
        self._load_legacy_settings(config_dict)

        # 2. Load global config
        self._load_global_config(config_dict)

        # 3. Load project config
        self._load_project_config(config_dict)

        # 4. Load local overrides (git-ignored)
        self._load_local_overrides(config_dict)

        # 5. Apply environment variables
        self._apply_env_vars(config_dict)

        # 6. Apply explicit overrides (highest priority)
        if overrides:
            self._apply_overrides(config_dict, overrides)
            self._loaded_sources.append("explicit overrides")

        # Create and validate config
        try:
            config = UnifiedConfig(**config_dict)
            logger.debug(
                f"Loaded configuration from {len(self._loaded_sources)} sources"
            )
            return config
        except Exception as e:
            logger.warning(f"Configuration validation failed: {e}")
            logger.info("Falling back to defaults with valid overrides")
            return self._create_fallback_config(config_dict)

    def _load_legacy_settings(self, config_dict: dict) -> None:
        """Load legacy settings.txt for backward compatibility."""
        # Check multiple locations for settings.txt
        settings_locations = [
            self.project_path / "settings.txt",
            Path(__file__).parent.parent.parent / "settings.txt",
        ]

        for settings_file in settings_locations:
            if settings_file.exists():
                legacy = load_legacy_settings(settings_file)
                if legacy:
                    self._convert_legacy_to_unified(legacy, config_dict)
                    self._loaded_sources.append(str(settings_file))
                    logger.debug(f"Loaded legacy settings from {settings_file}")
                break

    def _load_global_config(self, config_dict: dict) -> None:
        """Load global config from ~/.claude-indexer/config.json."""
        if ConfigPaths.GLOBAL_CONFIG.exists():
            try:
                with open(ConfigPaths.GLOBAL_CONFIG) as f:
                    global_config = json.load(f)
                _deep_merge(config_dict, global_config)
                self._loaded_sources.append(str(ConfigPaths.GLOBAL_CONFIG))
                logger.debug(f"Loaded global config from {ConfigPaths.GLOBAL_CONFIG}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in global config: {e}")
            except Exception as e:
                logger.warning(f"Failed to load global config: {e}")

    def _load_project_config(self, config_dict: dict) -> None:
        """Load project configuration with backward compatibility."""
        config_file = ConfigPaths.find_project_config(self.project_path)

        if config_file:
            try:
                with open(config_file) as f:
                    project_config = json.load(f)

                # Check version and convert if needed
                version = project_config.get("version", "2.6")
                if version < "3.0":
                    project_config = self._convert_v26_to_v30(project_config)
                    logger.info(f"Converted v{version} config to v3.0 format")

                _deep_merge(config_dict, project_config)
                self._loaded_sources.append(str(config_file))
                logger.debug(f"Loaded project config from {config_file}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in project config: {e}")
            except Exception as e:
                logger.warning(f"Failed to load project config: {e}")

        # Also load separate config files if they exist
        config_dir = ConfigPaths.get_project_config_dir(self.project_path)
        self._load_optional_config(
            config_dir / ConfigPaths.PROJECT_GUARD, config_dict, "guard"
        )
        self._load_optional_config(
            config_dir / ConfigPaths.PROJECT_MEMORY, config_dict, "indexing"
        )

    def _load_local_overrides(self, config_dict: dict) -> None:
        """Load local overrides (git-ignored settings)."""
        config_dir = ConfigPaths.get_project_config_dir(self.project_path)
        local_file = config_dir / ConfigPaths.PROJECT_LOCAL

        if local_file.exists():
            try:
                with open(local_file) as f:
                    local_config = json.load(f)
                _deep_merge(config_dict, local_config)
                self._loaded_sources.append(str(local_file))
                logger.debug(f"Loaded local overrides from {local_file}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in local overrides: {e}")
            except Exception as e:
                logger.warning(f"Failed to load local overrides: {e}")

    def _apply_env_vars(self, config_dict: dict) -> None:
        """Apply environment variable overrides."""
        applied = 0
        for env_var, path in self.ENV_MAPPINGS.items():
            value = os.environ.get(env_var)
            if value is not None:
                self._set_nested(config_dict, path, self._convert_value(value))
                applied += 1

        if applied > 0:
            self._loaded_sources.append(f"environment ({applied} vars)")
            logger.debug(f"Applied {applied} environment variables")

    def _apply_overrides(self, config_dict: dict, overrides: dict) -> None:
        """Apply explicit overrides with support for nested paths."""
        for key, value in overrides.items():
            if "." in key:
                # Support dot notation: "api.openai.api_key"
                path = tuple(key.split("."))
                self._set_nested(config_dict, path, value)
            elif isinstance(value, dict):
                if key not in config_dict:
                    config_dict[key] = {}
                if isinstance(config_dict[key], dict):
                    _deep_merge(config_dict[key], value)
                else:
                    config_dict[key] = value
            else:
                config_dict[key] = value

    def _load_optional_config(self, path: Path, config_dict: dict, key: str) -> None:
        """Load an optional config file into a specific key."""
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                if key not in config_dict:
                    config_dict[key] = {}
                if isinstance(config_dict[key], dict):
                    _deep_merge(config_dict[key], data)
                else:
                    config_dict[key] = data
                self._loaded_sources.append(str(path))
                logger.debug(f"Loaded optional config from {path}")
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")

    def _convert_legacy_to_unified(self, legacy: dict, config_dict: dict) -> None:
        """Convert legacy settings.txt format to unified format."""
        for old_key, new_path in self.LEGACY_MAPPINGS.items():
            if old_key in legacy:
                self._set_nested(config_dict, new_path, legacy[old_key])

        # Handle include/exclude patterns if present
        if "include_patterns" in legacy:
            self._set_nested(
                config_dict,
                ("indexing", "file_patterns", "include"),
                legacy["include_patterns"],
            )
        if "exclude_patterns" in legacy:
            self._set_nested(
                config_dict,
                ("indexing", "file_patterns", "exclude"),
                legacy["exclude_patterns"],
            )

        # Handle collection name
        if "collection_name" in legacy:
            # Need to ensure project dict exists
            if "project" not in config_dict:
                config_dict["project"] = {"name": "unnamed", "collection": "default"}
            if isinstance(config_dict["project"], dict):
                config_dict["project"]["collection"] = legacy["collection_name"]

    def _convert_v26_to_v30(self, config: dict) -> dict:
        """Convert v2.6 ProjectConfig to v3.0 UnifiedConfig format."""
        result: dict[str, Any] = {"version": "3.0"}

        # Project info
        if "project" in config:
            result["project"] = deepcopy(config["project"])

        # Indexing config
        if "indexing" in config:
            idx = config["indexing"]
            result["indexing"] = {
                "enabled": idx.get("enabled", True),
                "incremental": idx.get("incremental", True),
                "max_file_size": idx.get("max_file_size", 1048576),
            }
            if "file_patterns" in idx:
                result["indexing"]["file_patterns"] = deepcopy(idx["file_patterns"])
            if "parser_config" in idx:
                result["indexing"]["parser_config"] = deepcopy(idx["parser_config"])

        # Watcher config
        if "watcher" in config:
            result["watcher"] = deepcopy(config["watcher"])

        return result

    def _set_nested(self, d: dict, path: tuple[str, ...], value: Any) -> None:
        """Set a nested value in a dictionary.

        Args:
            d: Dictionary to modify.
            path: Tuple of keys representing the path.
            value: Value to set.
        """
        for key in path[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        d[path[-1]] = value

    def _convert_value(self, value: str) -> Any:
        """Convert string value to appropriate Python type.

        Args:
            value: String value to convert.

        Returns:
            Converted value (bool, int, float, or str).
        """
        # Boolean conversion
        if value.lower() in ("true", "false"):
            return value.lower() == "true"

        # Try integer
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        return value

    def _create_fallback_config(self, config_dict: dict) -> UnifiedConfig:
        """Create config with defaults, applying only valid values.

        Args:
            config_dict: Configuration dictionary with potentially invalid values.

        Returns:
            UnifiedConfig with defaults and valid overrides.
        """
        config = UnifiedConfig()

        # Try to apply valid values from config_dict
        valid_sections = [
            "api",
            "embedding",
            "indexing",
            "watcher",
            "performance",
            "hooks",
            "guard",
            "logging",
        ]

        for section in valid_sections:
            if section in config_dict and isinstance(config_dict[section], dict):
                try:
                    section_model = getattr(config, section)
                    for key, value in config_dict[section].items():
                        if hasattr(section_model, key):
                            try:
                                setattr(section_model, key, value)
                            except (ValueError, TypeError):
                                logger.debug(
                                    f"Skipping invalid value for {section}.{key}"
                                )
                except Exception as e:
                    logger.debug(f"Failed to apply section {section}: {e}")

        # Handle project separately
        if "project" in config_dict:
            try:
                project_data = config_dict["project"]
                if isinstance(project_data, dict):
                    config.project = ProjectInfo(
                        name=project_data.get("name", "unnamed"),
                        collection=project_data.get("collection", "default"),
                        description=project_data.get("description", ""),
                        project_type=project_data.get("project_type", "generic"),
                    )
            except Exception as e:
                logger.debug(f"Failed to apply project config: {e}")

        return config

    def get_loaded_sources(self) -> list[str]:
        """Return list of configuration sources that were loaded.

        Returns:
            List of source file paths and descriptions.
        """
        return self._loaded_sources.copy()


def load_unified_config(
    project_path: Path | None = None, **overrides: Any
) -> UnifiedConfig:
    """Load unified configuration from all sources.

    Convenience function that creates a HierarchicalConfigLoader and loads config.

    Args:
        project_path: Path to project root. Defaults to current directory.
        **overrides: Explicit configuration overrides.

    Returns:
        UnifiedConfig with all sources merged.
    """
    loader = HierarchicalConfigLoader(project_path)
    return loader.load(**overrides)
