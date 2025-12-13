"""
Workspace-level and per-folder configuration loading.

This module handles loading and merging configuration at the workspace level,
supporting hierarchical config inheritance from global to workspace to member.
"""

import json
from pathlib import Path
from typing import Any

from ..config.config_loader import ConfigLoader
from ..config.models import IndexerConfig
from ..indexer_logging import get_logger
from .types import WorkspaceConfig, WorkspaceMember

logger = get_logger()


class WorkspaceConfigLoader:
    """Loads and merges configuration at workspace level.

    Handles hierarchical configuration inheritance:
    1. Global configuration (lowest priority)
    2. Workspace-level configuration
    3. Member-specific configuration (highest priority)

    Configuration precedence (highest to lowest):
    1. Member-specific .claude-indexer/config.json
    2. Workspace-level .claude-indexer/workspace.config.json
    3. Global configuration

    Example:
        loader = WorkspaceConfigLoader(workspace_config)

        # Get config for specific member
        member_config = loader.get_member_config(member)

        # Get merged workspace settings
        workspace_settings = loader.get_workspace_settings()
    """

    WORKSPACE_CONFIG_FILE = "workspace.config.json"

    def __init__(
        self,
        workspace_config: WorkspaceConfig,
        base_config_loader: ConfigLoader | None = None,
    ):
        """Initialize workspace config loader.

        Args:
            workspace_config: WorkspaceConfig from detector
            base_config_loader: Optional base ConfigLoader for global config
        """
        self.workspace_config = workspace_config
        self.base_loader = base_config_loader or ConfigLoader()
        self._workspace_settings: dict[str, Any] | None = None

    def get_workspace_settings(self) -> dict[str, Any]:
        """Load workspace-level settings.

        Loads settings from workspace.config.json if it exists.
        Results are cached for subsequent calls.

        Returns:
            Dictionary of workspace settings
        """
        if self._workspace_settings is not None:
            return self._workspace_settings

        config_path = (
            self.workspace_config.root_path
            / ".claude-indexer"
            / self.WORKSPACE_CONFIG_FILE
        )

        if config_path.exists():
            try:
                with open(config_path) as f:
                    self._workspace_settings = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"Error loading workspace config: {e}")
                self._workspace_settings = {}
        else:
            self._workspace_settings = {}

        return self._workspace_settings

    def get_member_config(self, member: WorkspaceMember) -> IndexerConfig:
        """Get effective configuration for a workspace member.

        Merges global -> workspace -> member configs, with member
        taking highest precedence.

        Args:
            member: WorkspaceMember to get config for

        Returns:
            IndexerConfig with merged settings
        """
        # Start with base config (global)
        try:
            base_config = self.base_loader.load()
        except Exception as e:
            logger.debug(f"Error loading base config: {e}")
            base_config = IndexerConfig()

        # Get workspace-level overrides
        ws_settings = self.get_workspace_settings()

        # Apply workspace-level settings to base config
        if ws_settings:
            base_config = self._apply_settings_to_config(base_config, ws_settings)

        # Get member-specific overrides
        try:
            member_loader = ConfigLoader(member.path)
            member_config = member_loader.load()
            return member_config
        except Exception as e:
            logger.debug(f"No member-specific config for {member.name}: {e}")
            return base_config

    def _apply_settings_to_config(
        self, config: IndexerConfig, settings: dict[str, Any]
    ) -> IndexerConfig:
        """Apply settings dictionary to config.

        Args:
            config: Base IndexerConfig
            settings: Settings to apply

        Returns:
            Updated IndexerConfig
        """
        # Create a dict from the config and update with settings
        config_dict = config.model_dump()

        # Map settings keys to config keys
        key_mapping = {
            "include_patterns": "include_patterns",
            "exclude_patterns": "exclude_patterns",
            "collection_prefix": "collection_prefix",
            "embedding_provider": "embedding_provider",
        }

        for settings_key, config_key in key_mapping.items():
            if settings_key in settings:
                config_dict[config_key] = settings[settings_key]

        # Handle nested settings
        if "indexing" in settings:
            indexing = settings["indexing"]
            if "include_patterns" in indexing:
                config_dict["include_patterns"] = indexing["include_patterns"]
            if "exclude_patterns" in indexing:
                config_dict["exclude_patterns"] = indexing["exclude_patterns"]

        return IndexerConfig(**config_dict)

    def get_all_member_configs(self) -> dict[str, IndexerConfig]:
        """Get configs for all workspace members.

        Returns:
            Dictionary mapping member name to config
        """
        return {
            member.name: self.get_member_config(member)
            for member in self.workspace_config.members
        }

    def create_workspace_config(self, settings: dict[str, Any] | None = None) -> Path:
        """Create workspace configuration file.

        Creates workspace.config.json with initial settings
        and detected workspace information.

        Args:
            settings: Optional initial settings to include

        Returns:
            Path to created config file
        """
        config_dir = self.workspace_config.root_path / ".claude-indexer"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / self.WORKSPACE_CONFIG_FILE

        default_settings = {
            "workspace_type": self.workspace_config.workspace_type.value,
            "collection_strategy": self.workspace_config.collection_strategy.value,
            "collection_name": self.workspace_config.collection_name,
            "members": [
                {
                    "name": m.name,
                    "path": str(m.path),
                    "relative_path": m.relative_path,
                    "exclude": m.exclude_from_workspace,
                }
                for m in self.workspace_config.members
            ],
            "settings": settings or {},
        }

        with open(config_path, "w") as f:
            json.dump(default_settings, f, indent=2)

        logger.info(f"Created workspace config at {config_path}")
        return config_path

    def update_workspace_config(self, updates: dict[str, Any]) -> None:
        """Update workspace configuration.

        Merges updates into existing workspace config.

        Args:
            updates: Dictionary of updates to apply
        """
        config_path = (
            self.workspace_config.root_path
            / ".claude-indexer"
            / self.WORKSPACE_CONFIG_FILE
        )

        existing = {}
        if config_path.exists():
            try:
                with open(config_path) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        # Merge updates
        existing.update(updates)

        # Write back
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(existing, f, indent=2)

        # Clear cache
        self._workspace_settings = None

    def get_include_patterns(self) -> list[str]:
        """Get combined include patterns for workspace.

        Merges patterns from workspace config and base config.

        Returns:
            List of include patterns
        """
        ws_settings = self.get_workspace_settings()

        # Check workspace settings
        if "include_patterns" in ws_settings:
            return ws_settings["include_patterns"]

        if "settings" in ws_settings and "include_patterns" in ws_settings["settings"]:
            return ws_settings["settings"]["include_patterns"]

        # Fall back to base config
        try:
            base_config = self.base_loader.load()
            return base_config.include_patterns
        except Exception:
            return ["*.py", "*.js", "*.ts", "*.md"]

    def get_exclude_patterns(self) -> list[str]:
        """Get combined exclude patterns for workspace.

        Merges patterns from workspace config and base config.

        Returns:
            List of exclude patterns
        """
        ws_settings = self.get_workspace_settings()

        # Check workspace settings
        if "exclude_patterns" in ws_settings:
            return ws_settings["exclude_patterns"]

        if "settings" in ws_settings and "exclude_patterns" in ws_settings["settings"]:
            return ws_settings["settings"]["exclude_patterns"]

        # Fall back to base config
        try:
            base_config = self.base_loader.load()
            return base_config.exclude_patterns
        except Exception:
            return ["node_modules/", ".git/", "__pycache__/", "*.pyc"]
